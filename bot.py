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

# ⚠️ यहाँ अपनी असली टेलीग्राम न्यूमेरिकल आईडी डालें
ADMIN_ID = 7559016251  

# मोंगोडीबी सेटअप
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
posts_collection = db["posts"]

# Flask ऐप सेटअप
app = Flask(__name__)

# टेलीग्राम पर सीधे मैसेज भेजने का फंक्शन
def send_tg_message(chat_id, text, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

# नए कैप्शन (HTML) के साथ मीडिया भेजने का फंक्शन
def send_media_with_new_caption(chat_id, msg_data, caption):
    payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    
    # चेक करें कि यह फोटो है या वीडियो
    if "photo" in msg_data:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload["photo"] = msg_data["photo"][-1]["file_id"]
    elif "video" in msg_data:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
        payload["video"] = msg_data["video"]["file_id"]
    else:
        return False, "डेटा में कोई फोटो या वीडियो फ़ाइल नहीं मिली।"

    try:
        res = requests.post(url, json=payload).json()
        if res.get("ok"):
            return True, "सफलता"
        else:
            return False, res.get("description", "अन्वेषित त्रुटि")
    except Exception as e:
        return False, str(e)

# टेलीग्राम मैसेज प्रोसेसिंग का मुख्य फंक्शन
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

            # डेटाबेस से सबसे आखिरी पोस्ट खोजें
            last_post = posts_collection.find_one(sort=[("post_id", -1)])

            if last_post:
                prev_post_id = last_post["post_id"]
                prev_caption = last_post["caption"]
                prev_msg_raw = last_post.get("raw_data")

                start_video_id = prev_post_id + 1
                end_video_id = current_post_id - 1

                if start_video_id <= end_video_id:
                    if start_video_id == end_video_id:
                        bot_url = f"https://t.me/{TARGET_BOT_USER}?start={start_video_id}_{COMPULSORY_NUMBER}"
                    else:
                        bot_url = f"https://t.me/{TARGET_BOT_USER}?start={start_video_id}_{end_video_id}_{COMPULSORY_NUMBER}"

                    # HTML फॉर्मेटिंग का उपयोग (टेक्स्ट में लिंक छिपाने के लिए <a> टैग)
                    updated_caption = (
                        f"Best video\n"
                        f"{prev_caption}\n"
                        f'<a href="{bot_url}">Click here to watch</a>'
                    )

                    if prev_msg_raw:
                        for channel_id in TARGET_CHANNELS:
                            success, reason = send_media_with_new_caption(channel_id, prev_msg_raw, updated_caption)
                            if success:
                                send_tg_message(ADMIN_ID, f"📢 <b>चैनल अपडेट:</b>\nपुरानी पोस्ट आईडी <code>{prev_post_id}</code> नए कैप्शन के साथ चैनल <code>{channel_id}</code> में सफलतापूर्वक भेज दी गई है!")
                            else:
                                send_tg_message(ADMIN_ID, f"❌ <b>भेजने में त्रुटि ({channel_id}):</b> पोस्ट आईडी <code>{prev_post_id}</code> नहीं भेजी जा सकी।\nकारण: {reason}")
                    else:
                        send_tg_message(ADMIN_ID, f"⚠️ <b>सूचना:</b> पुरानी पोस्ट <code>{prev_post_id}</code> का मीडिया डेटाबेस में न होने के कारण कैप्शन नहीं बदला जा सका।")

            # नई पोस्ट को डेटाबेस में सेव करना
            try:
                posts_collection.insert_one({
                    "post_id": current_post_id,
                    "caption": current_caption,
                    "raw_data": msg_data
                })
                send_tg_message(ADMIN_ID, f"📥 <b>मोंगोडीबी अपडेट:</b>\nनई पोस्ट आईडी <code>{current_post_id}</code> सफलतापूर्वक डेटाबेस में सुरक्षित हो गई है!")
            except Exception as e:
                send_tg_message(ADMIN_ID, f"❌ <b>मोंगोडीबी त्रुटि:</b>\nपोस्ट आईडी <code>{current_post_id}</code> सेव करने में विफल। एरर: {str(e)}")

# Vercel के लिए वेबहुक एंडपॉइंट
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
