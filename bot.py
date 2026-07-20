import os
import logging
import asyncio
import random
import psycopg2
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- 1. KEEP-ALIVE SERVER (Flask) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running with Database!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. CONFIGURATION ---
BOT_TOKEN = "7805572091:AAGal4nWPVNsItMFa5WpN2KJUQpxYcgEbDs"
ADMIN_CHAT_ID = 5935470765
GROUP_CHAT_ID = -1004347063089
CHANNEL_CHAT_ID = -1003866567193
TELE_BIRR_NUMBER = "0912801444"
TICKET_PRICE = 100
TOTAL_TICKETS = 50

DATABASE_URL = os.environ.get('DATABASE_URL')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 3. DATABASE FUNCTIONS ---

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # ቲኬቶችን መያዣ
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            status TEXT DEFAULT '🟢',
            user_id BIGINT,
            user_name TEXT,
            expires_at TIMESTAMP
        )
    ''')
    # መልእክት መከታተያ (Message IDs) መያዣ
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

def get_all_tickets():
    conn = get_db_connection()
    cur = conn.cursor()
    # ጊዜያቸው ያለፈባቸውን (🟡) ወደ (🟢) መመለስ
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

# --- 4. BOT FUNCTIONS ---

def generate_keyboard():
    tickets_data = get_all_tickets()
    keyboard = []
    row = []
    for num, data in tickets_data.items():
        button_text = f"{num} {data['status']}"
        row.append(InlineKeyboardButton(button_text, callback_data=f"select_{num}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def update_live_messages(context: ContextTypes.DEFAULT_TYPE):
    text = "🎰 **የሎተሪ ቲኬቶች ዝርዝር**\n\n🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\nለመግዛት ቁጥር ይጫኑ።"
    reply_markup = generate_keyboard()
    g_id = get_setting("group_msg_id")
    c_id = get_setting("chan_msg_id")
    try:
        if g_id: await context.bot.edit_message_text(text, chat_id=GROUP_CHAT_ID, message_id=int(g_id), reply_markup=reply_markup, parse_mode="Markdown")
        if c_id: await context.bot.edit_message_text(text, chat_id=CHANNEL_CHAT_ID, message_id=int(c_id), reply_markup=reply_markup, parse_mode="Markdown")
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("select_"):
        ticket_num = int(context.args[0].split("_")[1])
        await handle_selection(update, context, ticket_num)
    else:
        await update.message.reply_text("እንኳን ደህና መጡ! ቲኬት ለመግዛት ግሩፑን ይጎብኙ።")

async def open_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    text = "🎰 **የሎተሪ ቲኬቶች ዝርዝር**\n\n🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\nለመግዛት ቁጥር ይጫኑ።"
    reply_markup = generate_keyboard()
    msg_g = await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    msg_c = await context.bot.send_message(chat_id=CHANNEL_CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    set_setting("group_msg_id", msg_g.message_id)
    set_setting("chan_msg_id", msg_c.message_id)
    await update.message.reply_text("✅ ሎተሪ ተከፍቷል።")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ticket_num = query.data.split("_")[1]
    bot_username = (await context.bot.get_me()).username
    await query.answer(url=f"https://t.me/{bot_username}?start=select_{ticket_num}")

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_num):
    user = update.effective_user
    tickets_data = get_all_tickets()
    ticket = tickets_data[ticket_num]
    if ticket["status"] == "🔴":
        await update.message.reply_text("ይቅርታ ይህ ቁጥር ተሽጧል።")
        return
    expiry = datetime.now() + timedelta(minutes=30)
    update_ticket(ticket_num, '🟡', user.id, user.full_name, expiry)
    await update.message.reply_text(f"ቁጥር {ticket_num} ተይዞልዎታል። በ {TELE_BIRR_NUMBER} ብር 100 ልከው ደረሰኝ እዚህ ይላኩ።")
    await update_live_messages(context)

async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tickets_data = get_all_tickets()
    ticket_num = next((id for id, d in tickets_data.items() if d["user_id"] == user.id and d["status"] == "🟡"), None)
    if not ticket_num:
        await update.message.reply_text("መጀመሪያ ቁጥር ይምረጡ።")
        return
    caption = f"የክፍያ ማረጋገጫ፡\nቲኬት፡ {ticket_num}\nUser ID: {user.id}\nስም፡ {user.full_name}"
    if update.message.photo:
        await context.bot.send_photo(ADMIN_CHAT_ID, update.message.photo[-1].file_id, caption=caption)
    elif update.message.text:
        await context.bot.send_message(ADMIN_CHAT_ID, f"{caption}\n\n{update.message.text}")
    await update.message.reply_text("ለአስተዳዳሪ ተልኳል።")

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
    except: return

    if "/approve" in text:
        update_ticket(tnum, '🔴', uid, name, None)
        await context.bot.send_message(uid, f"እንኳን ደስ አለዎት! ቁጥር {tnum} ጸድቋል።")
        await update.message.reply_text(f"ቁጥር {tnum} ጸድቋል።")
    elif "/reject" in text:
        update_ticket(tnum, '🟢', None, None, None)
        await context.bot.send_message(uid, f"ክፍያዎ ለቁጥር {tnum} ውድቅ ተደርጓል።")
        await update.message.reply_text(f"ቁጥር {tnum} ውድቅ ሆኗል።")
    await update_live_messages(context)

async def pick_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, user_name FROM tickets WHERE status = '🔴'")
    sold = cur.fetchall()
    cur.close(); conn.close()
    if not sold:
        await update.message.reply_text("የተሸጠ ቲኬት የለም።")
        return
    win = random.choice(sold)
    win_text = f"🎊 አሸናፊው ታውቋል! 🎊\n\nቁጥር፡ {win[0]}\nአሸናፊ፡ {win[1]}"
    await context.bot.send_message(GROUP_CHAT_ID, win_text)
    await context.bot.send_message(CHANNEL_CHAT_ID, win_text)

# --- 5. MAIN ---
def main():
    init_db()
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("open", open_lottery))
    application.add_handler(CommandHandler("winner", pick_winner))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_CHAT_ID), admin_decision))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.PHOTO | filters.TEXT) & ~filters.COMMAND, handle_proof))

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
