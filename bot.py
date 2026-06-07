import os
import dns.resolver
import requests
from flask import Flask, request, jsonify
from pymongo import MongoClient

try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
except Exception:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = "telegram_tracker"

MONITOR_CHANNEL = -1003758252316  
TARGET_CHANNELS = [-1003925609024, -1003628942216, -1003835409098]  
TARGET_BOT_USER = "Getvideo81827_bot"
COMPULSORY_NUMBER = "2"

ADMIN_ID = 7559016251  # अपनी असली आईडी सुनिश्चित करें

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
posts_collection = db["posts"]

app = Flask(__name__)

def send_tg_message(chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try: requests.post(url, json=payload)
    except Exception: pass

def forward_tg_message(chat_id, from_chat_id, message_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/forwardMessage"
    payload = {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id}
    try:
        res = requests.post(url, json=payload).json()
        return res.get("ok", False)
    except Exception:
        return False

def process_telegram_message(msg_data, is_channel=False):
    if not is_channel:
        chat_id = msg_data.get("chat", {}).get("id")
        text = msg_data.get("text", "")
        if text.startswith("/start"):
            send_tg_message(chat_id, "✅ बॉट पूरी तरह सक्रिय है और आपके चैनल की निगरानी कर रहा है!")
            return

    if is_channel:
        chat_id = msg_data.get("chat", {}).get("id")
        
        if chat_id == MONITOR_CHANNEL:
            if "caption" not in msg_data or not msg_data.get("caption"):
                return

            current_post_id = msg_data.get("message_id")
            current_caption = msg_data.get("caption")

            last_post = posts_collection.find_one(sort=[("post_id", -1)])

            if last_post:
                prev_post_id = last_post["post_id"]
                prev_caption = last_post["caption"]

                start_video_id = prev_post_id + 1
                end_video_id = current_post_id - 1

                if start_video_id <= end_video_id:
                    if start_video_id == end_video_id:
                        bot_url = f"https://t.me/{TARGET_BOT_USER}?start={start_video_id}_{COMPULSORY_NUMBER}"
                    else:
                        bot_url = f"https://t.me/{TARGET_BOT_USER}?start={start_video_id}_{end_video_id}_{COMPULSORY_NUMBER}"

                    updated_caption = (
                        f"Best video\n"
                        f"{prev_caption}\n"
                        f"[Click here to watch]({bot_url})"
                    )

                    # पहले चैनलों में पुरानी पोस्ट फॉरवर्ड करें
                    for channel_id in TARGET_CHANNELS:
                        success = forward_tg_message(channel_id, MONITOR_CHANNEL, prev_post_id)
                        if success:
                            # फॉरवर्ड होने के बाद उसका नया कैप्शन अलग से नीचे भेजें
                            send_tg_message(channel_id, updated_caption)
                            send_tg_message(ADMIN_ID, f"📢 **चैनल अपडेट:**\nपोस्ट आईडी `{prev_post_id}` सफलतापूर्वक चैनल `{channel_id}` में फॉरवर्ड कर दी गई है!")
                        else:
                            send_tg_message(ADMIN_ID, f"❌ **फॉरवर्ड त्रुटि:** चैनल `{channel_id}` में पोस्ट आईडी `{prev_post_id}` भेजने में विफलता।")

            try:
                posts_collection.insert_one({"post_id": current_post_id, "caption": current_caption})
                send_tg_message(ADMIN_ID, f"📥 **मोंगोडीबी अपडेट:**\nनई पोस्ट आईडी `{current_post_id}` सफलतापूर्वक डेटाबेस में सुरक्षित हो गई है!")
            except Exception as e:
                send_tg_message(ADMIN_ID, f"❌ **मोंगोडीबी त्रुटि:** {str(e)}")

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        data = request.get_json()
        if "message" in data:
            process_telegram_message(data["message"], is_channel=False)
        elif "channel_post" in data:
            msg_data = data["channel_post"]
            if "video" in msg_data or "photo" in msg_data:
                process_telegram_message(msg_data, is_channel=True)
        return "OK", 200
    return "Forbidden", 403

@app.route("/", methods=["GET"])
def index():
    return "बॉट वेबहुक सक्रिय है!", 200
