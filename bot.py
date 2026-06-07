import os
import dns.resolver
import requests
from flask import Flask, request, jsonify
from pymongo import MongoClient

# --- एंड्रॉइड फिक्स ---
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
except Exception:
    pass

# --- पर्यावरण वेरिएबल्स (Environment Variables) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = "telegram_tracker"

# --- चैनल और सेटिंग्स ---
MONITOR_CHANNEL = -1003758252316  
TARGET_CHANNELS = [-1003925609024, -1003628942216, -1003835409098]  
TARGET_BOT_USER = "Getvideo81827_bot"
COMPULSORY_NUMBER = "2"

# ⚠️ यहाँ अपनी असली टेलीग्राम न्यूमेरिकल आईडी डालें (जैसे: 543216789)
ADMIN_ID = 7559016251  

# मोंगोडीबी सेटअप
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
posts_collection = db["posts"]

# Flask ऐप सेटअप
app = Flask(__name__)

# टेलीग्राम API को सीधे रिक्वेस्ट भेजने के लिए फंक्शन्स
def send_tg_message(chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": False}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

def copy_tg_message(chat_id, from_chat_id, message_id, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage"
    payload = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload).json()
        return res.get("ok", False)
    except Exception as e:
        print(f"Error copying message: {e}")
        return False

# टेलीग्राम मैसेज प्रोसेसिंग का मुख्य फंक्शन
def process_telegram_message(msg_data, is_channel=False):
    # 1. पर्सनल चैट में /start कमांड का जवाब देना
    if not is_channel:
        chat_id = msg_data.get("chat", {}).get("id")
        text = msg_data.get("text", "")
        if text.startswith("/start"):
            send_tg_message(chat_id, "✅ बॉट पूरी तरह सक्रिय है और आपके चैनल की निगरानी कर रहा है!")
            return

    # 2. चैनल पोस्ट की निगरानी करना
    if is_channel:
        chat_id = msg_data.get("chat", {}).get("id")
        
        # केवल तभी काम करें जब यह सही मॉनिटर चैनल हो
        if chat_id == MONITOR_CHANNEL:
            # अगर कैप्शन नहीं है, तो सीधे छोड़ दें (वीडियो/क्लिप्स को इग्नोर करें)
            if "caption" not in msg_data or not msg_data.get("caption"):
                return

            current_post_id = msg_data.get("message_id")
            current_caption = msg_data.get("caption")

            # डेटाबेस से सबसे आखिरी पोस्ट खोजें
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

                    # यहाँ टेलीग्राम के नियमों के अनुसार [Text](Link) फॉर्मेट का उपयोग किया गया है
                    updated_caption = (
                        f"Best video\n"
                        f"{prev_caption}\n"
                        f"[Click here to watch]({bot_url})"
                    )

                    # तीनों चैनलों में पुरानी पोस्ट कॉपी करें
                    for channel_id in TARGET_CHANNELS:
                        success = copy_tg_message(channel_id, MONITOR_CHANNEL, prev_post_id, updated_caption)
                        if success:
                            send_tg_message(ADMIN_ID, f"📢 **चैनल अपडेट:**\nपोस्ट आईडी `{prev_post_id}` सफलतापूर्वक चैनल `{channel_id}` में कॉपी कर दी गई है!")
                        else:
                            send_tg_message(ADMIN_ID, f"❌ **कॉपी त्रुटि:** चैनल `{channel_id}` में पोस्ट आईडी `{prev_post_id}` भेजने में विफलता। कृपया चेक करें कि बॉट वहां एडमिन है या नहीं।")

            # नई पोस्ट डेटाबेस में सेव करें और एडमिन को सूचित करें
            try:
                posts_collection.insert_one({
                    "post_id": current_post_id,
                    "caption": current_caption
                })
                send_tg_message(ADMIN_ID, f"📥 **मोंगोडीबी अपडेट:**\nनई पोस्ट आईडी `{current_post_id}` सफलतापूर्वक डेटाबेस में सुरक्षित हो गई है!")
            except Exception as e:
                send_tg_message(ADMIN_ID, f"❌ **मोंगोडीबी त्रुटि:**\nपोस्ट आईडी `{current_post_id}` सेव करने में विफल। एरर: {str(e)}")

# Vercel के लिए वेबहुक एंडपॉइंट
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        data = request.get_json()
        
        # 1. सामान्य मैसेज (जैसे /start)
        if "message" in data:
            process_telegram_message(data["message"], is_channel=False)
            
        # 2. चैनल पोस्ट (मुख्य चैनल की पोस्ट और वीडियोस)
        elif "channel_post" in data:
            msg_data = data["channel_post"]
            # सिर्फ वीडियो या फोटो होने पर ही आगे बढ़ें
            if "video" in msg_data or "photo" in msg_data:
                process_telegram_message(msg_data, is_channel=True)
                
        return "OK", 200
    return "Forbidden", 403

@app.route("/", methods=["GET"])
def index():
    return "बॉट वेबहुक सक्रिय है!", 200
