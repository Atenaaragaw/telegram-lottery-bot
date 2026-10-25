import os

# --- ደህንነታቸው የተጠበቁ እና ዋና ማዋቀሪያዎች (CONFIG & SECRETS) ---
# ቶከኑን ከ Environment Variable ማንበብ የሚችል ሲሆን ካልተገኘ በኮድ ውስጥ ባለው ቴምፕሌት ይተካል
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8900641412:AAGuK4sE6o65dNTrIIpDXHHRndfZV0QhOmY")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", 5935470765))
GROUP_CHAT_ID = int(os.environ.get("GROUP_CHAT_ID", -1004347063089))
CHANNEL_CHAT_ID = int(os.environ.get("CHANNEL_CHAT_ID", -1003866567193))

GROUP_INVITE_LINK = "https://t.me/Addis_lottery"
TELE_BIRR_NUMBER = "0912801444"
TICKET_PRICE = 100
TOTAL_TICKETS = 50

# የዳታቤዝ ዩአርኤል ከ Render Environment Variable ይነበባል
DATABASE_URL = os.environ.get('DATABASE_URL')
