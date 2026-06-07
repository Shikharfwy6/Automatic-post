import os
import asyncio
import dns.resolver
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.types import Message, Chat
from pymongo import MongoClient

# --- एंड्रॉइड फिक्स ---
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
except Exception:
    pass

# --- पर्यावरण वेरिएबल्स (Environment Variables) ---
API_ID = int(os.environ.get("API_ID", 1234567))
API_HASH = os.environ.get("API_HASH")
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

# टेलीग्राम क्लाइंट सेटअप
app_tg = Client(
    "channel_tracker", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    workers=1, 
    in_memory=True
)

# Flask ऐप सेटअप
app = Flask(__name__)

# टेलीग्राम मैसेज प्रोसेसिंग का मुख्य फंक्शन
async def process_telegram_message(message: Message, is_channel=False):
    # 1. पर्सनल चैट में /start कमांड का जवाब देना (केवल सामान्य मैसेज के लिए)
    if not is_channel and message.text and message.text.startswith("/start"):
        try:
            await app_tg.send_message(chat_id=message.chat.id, text="✅ बॉट पूरी तरह सक्रिय है और आपके चैनल की निगरानी कर रहा है!")
        except Exception as e:
            print(f"Error sending start reply: {e}")
        return

    # 2. चैनल पोस्ट की निगरानी करना
    if is_channel and message.chat and message.chat.id == MONITOR_CHANNEL:
        # अगर कैप्शन नहीं है, तो सीधे छोड़ दें
        if not message.caption:
            return

        current_post_id = message.id
        current_caption = message.caption

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

                updated_caption = (
                    f"Best video\n"
                    f"{prev_caption}\n"
                    f"[Click here to watch]({bot_url})"
                )

                # चैनलों में पोस्ट कॉपी करें
                for channel_id in TARGET_CHANNELS:
                    try:
                        await app_tg.copy_message(
                            chat_id=channel_id,
                            from_chat_id=MONITOR_CHANNEL,
                            message_id=prev_post_id,
                            caption=updated_caption
                        )
                        # सफलता का लॉग एडमिन को भेजना
                        await app_tg.send_message(
                            chat_id=ADMIN_ID,
                            text=f"📢 **चैनल अपडेट:**\nपोस्ट आईडी `{prev_post_id}` को नए कैप्शन के साथ सफलतापूर्वक चैनल `{channel_id}` में कॉपी कर दिया गया है!"
                        )
                    except Exception as e:
                        try:
                            await app_tg.send_message(
                                chat_id=ADMIN_ID,
                                text=f"❌ **कॉपी त्रुटि ({channel_id}):** {str(e)}"
                            )
                        except Exception:
                            pass

        # नई पोस्ट डेटाबेस में सेव करें और आपको सूचित करें
        try:
            posts_collection.insert_one({
                "post_id": current_post_id,
                "caption": current_caption
            })
            # एडमिन को पर्सनल नोटिफिकेशन भेजना
            await app_tg.send_message(
                chat_id=ADMIN_ID, 
                text=f"📥 **मोंगोडीबी अपडेट:**\nनई पोस्ट आईडी `{current_post_id}` सफलतापूर्वक डेटाबेस में सुरक्षित हो गई है!"
            )
        except Exception as e:
            try:
                await app_tg.send_message(
                    chat_id=ADMIN_ID, 
                    text=f"❌ **मोंगोडीबी त्रुटि:**\nपोस्ट आईडी `{current_post_id}` सेव करने में विफल। एरर: {str(e)}"
                )
            except Exception:
                pass

# Vercel के लिए वेबहुक एंडपॉइंट
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        data = request.get_json()
        
        async def handle():
            if not app_tg.is_connected:
                await app_tg.connect()
            
            # 1. सामान्य मैसेज (जैसे /start)
            if "message" in data:
                msg_data = data["message"]
                msg = Message(
                    id=msg_data.get("message_id"),
                    client=app_tg,
                    text=msg_data.get("text"),
                    chat=Chat(id=msg_data["chat"]["id"], type=msg_data["chat"]["type"], client=app_tg) if "chat" in msg_data else None
                )
                await process_telegram_message(msg, is_channel=False)
                
            # 2. चैनल पोस्ट (मुख्य चैनल की पोस्ट और वीडियोस)
            elif "channel_post" in data:
                msg_data = data["channel_post"]
                # सिर्फ वीडियो या फोटो होने पर ही प्रोसेस करें
                if "video" in msg_data or "photo" in msg_data:
                    msg = Message(
                        id=msg_data.get("message_id"),
                        client=app_tg,
                        caption=msg_data.get("caption"),
                        chat=Chat(id=msg_data["chat"]["id"], type=msg_data["chat"]["type"], client=app_tg) if "chat" in msg_data else None
                    )
                    await process_telegram_message(msg, is_channel=True)
                    
        asyncio.run(handle())
        return "OK", 200
    return "Forbidden", 403

@app.route("/", methods=["GET"])
def index():
    return "बॉट वेबहुक सक्रिय है!", 200
