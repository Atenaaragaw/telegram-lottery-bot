import os
import logging
import asyncio
import random
import psycopg2
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. KEEP-ALIVE ሰርቨር (Render ቦቱን እንዳያዘጋው) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running with DB and Deep Links!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. ማዋቀሪያ (CONFIG) ---
BOT_TOKEN = "7805572091:AAGal4nWPVNsItMFa5WpN2KJUQpxYcgEbDs"
ADMIN_CHAT_ID = 5935470765
GROUP_CHAT_ID = -1004347063089
CHANNEL_CHAT_ID = -1003866567193
TELE_BIRR_NUMBER = "0912801444"
TICKET_PRICE = 100
TOTAL_TICKETS = 50

# Render Environment Variable (DATABASE_URL)
DATABASE_URL = os.environ.get('DATABASE_URL')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 3. ዳታቤዝ ተግባራት (DATABASE) ---

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            status TEXT DEFAULT '🟢',
            user_id BIGINT,
            user_name TEXT,
            expires_at TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cur.execute("SELECT COUNT(*) FROM tickets")
    if cur.fetchone()[0] == 0:
        for i in range(1, TOTAL_TICKETS + 1):
            cur.execute("INSERT INTO tickets (id, status) VALUES (%s, %s)", (i, '🟢'))
    conn.commit()
    cur.close()
    conn.close()

def get_all_tickets():
    conn = get_db_connection()
    cur = conn.cursor()
    # የ30 ደቂቃ ገደብ ያለፈባቸውን መልሶ ክፍት ማድረግ
    cur.execute('''
        UPDATE tickets SET status = '🟢', user_id = NULL, expires_at = NULL 
        WHERE status = '🟡' AND expires_at < %s
    ''', (datetime.now(),))
    conn.commit()
    cur.execute("SELECT id, status, user_id, user_name FROM tickets ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r[0]: {"status": r[1], "user_id": r[2], "user_name": r[3]} for r in rows}

def update_ticket(ticket_id, status, user_id=None, user_name=None, expires_at=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE tickets SET status = %s, user_id = %s, user_name = %s, expires_at = %s 
        WHERE id = %s
    ''', (status, user_id, user_name, expires_at, ticket_id))
    conn.commit()
    cur.close()
    conn.close()

def set_setting(key, value):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, str(value)))
    conn.commit()
    cur.close()
    conn.close()

def get_setting(key):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

# --- 4. ቦት ተግባራት (BOT FUNCTIONS) ---

def generate_keyboard(bot_username):
    """ቁጥሮቹን ሲጫኑ በቀጥታ ወደ ቦቱ የሚወስድ (Deep Link) አዝራር ይፈጥራል"""
    tickets_data = get_all_tickets()
    keyboard = []
    row = []
    for num, data in tickets_data.items():
        status_icon = data['status']
        # እያንዳንዱ ቁጥር የራሱ ሊንክ አለው
        url = f"https://t.me/{bot_username}?start=select_{num}"
        button_text = f"{num} {status_icon}"
        row.append(InlineKeyboardButton(button_text, url=url))
        
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def update_live_messages(context: ContextTypes.DEFAULT_TYPE):
    """ግሩፕ እና ቻናል ላይ ያለውን ሰንጠረዥ ያድሳል"""
    bot_info = await context.bot.get_me()
    text = (
        "🎰 **የሎተሪ ቲኬቶች ዝርዝር**\n\n"
        "🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\n"
        "ለመግዛት የፈለጉትን ቁጥር ይጫኑ።"
    )
    reply_markup = generate_keyboard(bot_info.username)
    
    g_id = get_setting("group_msg_id")
    c_id = get_setting("chan_msg_id")
    
    try:
        if g_id: await context.bot.edit_message_text(text, chat_id=GROUP_CHAT_ID, message_id=int(g_id), reply_markup=reply_markup, parse_mode="Markdown")
        if c_id: await context.bot.edit_message_text(text, chat_id=CHANNEL_CHAT_ID, message_id=int(c_id), reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Update error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # ከግሩፕ ቁጥር ተጭኖ ሲመጣ (e.g., /start select_5)
    if context.args and context.args[0].startswith("select_"):
        try:
            ticket_num = int(context.args[0].split("_")[1])
            await handle_selection(update, context, ticket_num)
        except:
            await update.message.reply_text("ስህተት ተከስቷል። እባክዎ እንደገና ይሞክሩ።")
    else:
        await update.message.reply_text(f"ሰላም {user.first_name}! እንኳን ወደ ሎተሪ ቦት መጡ። ቲኬት ለመግዛት ግሩፑን ይጎብኙ።")

async def open_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    bot_info = await context.bot.get_me()
    text = "🎰 **የሎተሪ ቲኬቶች ዝርዝር ተከፍቷል!**\n\n🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ"
    reply_markup = generate_keyboard(bot_info.username)
    
    msg_g = await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    msg_c = await context.bot.send_message(chat_id=CHANNEL_CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    
    set_setting("group_msg_id", msg_g.message_id)
    set_setting("chan_msg_id", msg_c.message_id)
    await update.message.reply_text("✅ ሎተሪው በግሩፕ እና በቻናል ላይ ተለጥፏል።")

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_num):
    user = update.effective_user
    tickets_data = get_all_tickets()
    
    if ticket_num not in tickets_data: return
    ticket = tickets_data[ticket_num]

    if ticket["status"] == "🔴":
        await update.message.reply_text("❌ ይቅርታ፣ ይህ ቲኬት ቀደም ብሎ ተሽጧል።")
        return
    
    if ticket["status"] == "🟡" and ticket["user_id"] != user.id:
        await update.message.reply_text("⚠️ ይህ ቁጥር ሌላ ሰው ሊገዛው ሙከራ ላይ ነው።")
        return

    # ቲኬቱን በዳታቤዝ 'Pending' ማድረግ
    expiry = datetime.now() + timedelta(minutes=30)
    update_ticket(ticket_num, '🟡', user.id, user.full_name, expiry)
    
    payment_msg = (
        f"✅ ለቁጥር **{ticket_num}** ቲኬት መርጠዋል።\n\n"
        f"💵 ዋጋ፡ **{TICKET_PRICE} ብር**\n"
        f"📱 ቴሌብር ስልክ፡ `{TELE_BIRR_NUMBER}`\n\n"
        "ክፍያውን እንደፈጸሙ የደረሰኝ ፎቶ እዚህ ይላኩ። ቁጥሩ ለ30 ደቂቃ ይቆይልዎታል።"
    )
    await update.message.reply_text(payment_msg, parse_mode="Markdown")
    await update_live_messages(context)

async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tickets_data = get_all_tickets()
    ticket_num = next((id for id, d in tickets_data.items() if d["user_id"] == user.id and d["status"] == "🟡"), None)

    if not ticket_num:
        await update.message.reply_text("ምንም በመጠባበቅ ላይ ያለ ቲኬት የለዎትም። መጀመሪያ ቁጥር ይምረጡ።")
        return

    caption = f"📩 የክፍያ ማረጋገጫ፡\nቲኬት፡ {ticket_num}\nUser ID: {user.id}\nስም፡ {user.full_name}"
    
    if update.message.photo:
        await context.bot.send_photo(ADMIN_CHAT_ID, update.message.photo[-1].file_id, caption=caption)
    elif update.message.text:
        await context.bot.send_message(ADMIN_CHAT_ID, f"{caption}\n\nጽሑፍ፡\n{update.message.text}")
    
    await update.message.reply_text("✅ ማረጋገጫው ለአስተዳዳሪ ተልኳል። ሲጸድቅ መልእክት ይደርስዎታል።")

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID or not update.message.reply_to_message: return
    
    text = update.message.text.lower()
    reply = update.message.reply_to_message
    content = reply.caption or reply.text
    if "User ID:" not in content: return

    try:
        uid = int(content.split("User ID:")[1].split("\n")[0].strip())
        tnum = int(content.split("ቲኬት፡")[1].split("\n")[0].strip())
        name = content.split("ስም፡")[1].strip()
    except:
        await update.message.reply_text("ስህተት፡ መረጃውን ማንበብ አልተቻለም።")
        return

    if "/approve" in text:
        update_ticket(tnum, '🔴', uid, name, None)
        await context.bot.send_message(uid, f"🎉 እንኳን ደስ አለዎት! ቁጥር {tnum} ጸድቋል። መልካም ዕድል!")
        await update.message.reply_text(f"✅ ቁጥር {tnum} ተረጋግጧል።")
    elif "/reject" in text:
        update_ticket(tnum, '🟢', None, None, None)
        await context.bot.send_message(uid, f"❌ ይቅርታ፣ ለቁጥር {tnum} የላኩት ክፍያ ተቀባይነት አላገኘም።")
        await update.message.reply_text(f"❌ ቁጥር {tnum} ውድቅ ተደርጓል።")
    
    await update_live_messages(context)

async def pick_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, user_name FROM tickets WHERE status = '🔴'")
    sold = cur.fetchall()
    cur.close(); conn.close()
    
    if not sold:
        await update.message.reply_text("ምንም የተሸጠ ቲኬት የለም።")
        return
    
    win = random.choice(sold)
    win_text = f"🎊 **የሎተሪው አሸናፊ ታውቋል!** 🎊\n\nዕድለኛ ቁጥር፡ **{win[0]}**\nአሸናፊ፡ **{win[1]}**\n\nእንኳን ደስ አላችሁ! 🎁"
    
    await context.bot.send_message(GROUP_CHAT_ID, win_text, parse_mode="Markdown")
    await context.bot.send_message(CHANNEL_CHAT_ID, win_text, parse_mode="Markdown")

# --- 5. ዋና ማስጀመሪያ (MAIN) ---

def main():
    init_db()
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("open", open_lottery))
    application.add_handler(CommandHandler("winner", pick_winner))
    
    # አስተዳዳሪው ደረሰኝ ላይ ሪፕላይ ሲያደርግ
    application.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_CHAT_ID), admin_decision))
    
    # ክፍያ ማረጋገጫ መቀበያ (ትዕዛዝ ያልሆኑ ጽሑፎችና ፎቶዎች)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.PHOTO | filters.TEXT) & ~filters.COMMAND, handle_proof))

    print("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
