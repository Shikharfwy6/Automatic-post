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
MONITOR_CHANNEL = -1003758252316  # मुख्य चैनल
TARGET_CHANNELS = [-1003925609024, -1003628942216, -1003835409098]  # आपके 3 टारगेट चैनल

TARGET_BOT_USER = "Getvideo81827_bot"
COMPULSORY_NUMBER = "2"

# ⚠️ यहाँ अपनी असली टेलीग्राम न्यूमेरिकल आईडी डालें ताकि बॉट आपको लॉग्स भेज सके
ADMIN_ID = 7559016251  

# मोंगोडीबी सेटअप
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
posts_collection = db["posts"]

# Flask ऐप सेटअप
app = Flask(__name__)

# टेलीग्राम पर सीधे मैसेज भेजने का फंक्शन
def send_tg_message(chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": False}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

# नए कैप्शन के साथ मीडिया भेजने का मुख्य फंक्शन (लॉजिक को काम कराने के लिए)
def send_media_with_new_caption(chat_id, msg_data, caption):
    # जाँच करें कि मीडिया फ़ोटो है या वीडियो और उसकी file_id निकालें
    if "photo" in msg_data:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        # टेलीग्राम सबसे बड़ी साइज की फोटो लिस्ट के आखिर में देता है
        media_id = msg_data["photo"][-1]["file_id"]
        payload = {"chat_id": chat_id, "photo": media_id, "caption": caption, "parse_mode": "Markdown"}
    elif "video" in msg_data:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
        media_id = msg_data["video"]["file_id"]
        payload = {"chat_id": chat_id, "video": media_id, "caption": caption, "parse_mode": "Markdown"}
    else:
        return False

    try:
        res = requests.post(url, json=payload).json()
        return res.get("ok", False)
    except Exception as e:
        print(f"Error sending media: {e}")
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

    # 2. चैनल की पोस्ट पर काम करना
    if is_channel:
        chat_id = msg_data.get("chat", {}).get("id")
        
        if chat_id == MONITOR_CHANNEL:
            # अगर कैप्शन नहीं है, तो सीधे छोड़ दें (वीडियो फाइल्स/क्लिप्स को छोड़ देगा)
            if "caption" not in msg_data or not msg_data.get("caption"):
                return

            current_post_id = msg_data.get("message_id")
            current_caption = msg_data.get("caption")

            # डेटाबेस से सबसे आखिरी पोस्ट खोजें
            last_post = posts_collection.find_one(sort=[("post_id", -1)])

            if last_post:
                prev_post_id = last_post["post_id"]
                prev_caption = last_post["caption"]
                prev_msg_raw = last_post.get("raw_data") # पुरानी पोस्ट का मीडिया डेटा

                start_video_id = prev_post_id + 1
                end_video_id = current_post_id - 1

                # आपके लॉजिक के अनुसार रेंज की जांच
                if start_video_id <= end_video_id:
                    if start_video_id == end_video_id:
                        bot_url = f"https://t.me/{TARGET_BOT_USER}?start={start_video_id}_{COMPULSORY_NUMBER}"
                    else:
                        bot_url = f"https://t.me/{TARGET_BOT_USER}?start={start_video_id}_{end_video_id}_{COMPULSORY_NUMBER}"

                    # आपका ओरिजिनल कैप्शन लॉजिक यहाँ है
                    updated_caption = (
                        f"Best video\n"
                        f"{prev_caption}\n"
                        f"[Click here to watch]({bot_url})"
                    )

                    # अगर पिछली पोस्ट का मीडिया डेटा मोंगोडीबी में मौजूद है
                    if prev_msg_raw:
                        for channel_id in TARGET_CHANNELS:
                            success = send_media_with_new_caption(channel_id, prev_msg_raw, updated_caption)
                            if success:
                                send_tg_message(ADMIN_ID, f"📢 **चैनल अपडेट:**\nपुरानी पोस्ट आईडी `{prev_post_id}` नए कैप्शन और लिंक के साथ चैनल `{channel_id}` में सफलतापूर्वक भेज दी गई है!")
                            else:
                                send_tg_message(ADMIN_ID, f"❌ **भेजने में त्रुटि:** चैनल `{channel_id}` में पोस्ट आईडी `{prev_post_id}` नए कैप्शन के साथ नहीं भेजी जा सकी।")
                    else:
                        send_tg_message(ADMIN_ID, f"⚠️ **सूचना:** पुरानी पोस्ट `{prev_post_id}` का मीडिया डेटाबेस में न होने के कारण कैप्शन नहीं बदला जा सका। यह केवल अगली नई पोस्ट्स से काम करेगा।")

            # नई पोस्ट को उसके पूरे मीडिया डेटा (raw_data) के साथ मोंगोडीबी में सेव करें
            try:
                posts_collection.insert_one({
                    "post_id": current_post_id,
                    "caption": current_caption,
                    "raw_data": msg_data  # यह मीडिया टाइप और file_id को सुरक्षित रखता है
                })
                send_tg_message(ADMIN_ID, f"📥 **मोंगोडीबी अपडेट:**\nनई पोस्ट आईडी `{current_post_id}` सफलतापूर्वक डेटाबेस में सुरक्षित हो गई है!")
            except Exception as e:
                send_tg_message(ADMIN_ID, f"❌ **मोंगोडीबी त्रुटि:**\nपोस्ट आईडी `{current_post_id}` सेव करने में विफल। एरर: {str(e)}")

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
