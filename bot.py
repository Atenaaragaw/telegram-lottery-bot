import os
import logging
import asyncio
import random
import psycopg2 # PostgreSQL ለመጠቀም
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

# Render የሚሰጠን የዳታቤዝ አድራሻ (URL)
DATABASE_URL = os.environ.get('DATABASE_URL')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 3. DATABASE FUNCTIONS ---

def get_db_connection():
    # ዳታቤዙን ለማገናኘት
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    """ዳታቤዙን እና ሰንጠረዡን ለመፍጠር"""
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
    # 50 ቲኬቶች ከሌሉ ለመጨመር
    cur.execute("SELECT COUNT(*) FROM tickets")
    if cur.fetchone()[0] == 0:
        for i in range(1, TOTAL_TICKETS + 1):
            cur.execute("INSERT INTO tickets (id, status) VALUES (%s, %s)", (i, '🟢'))
    conn.commit()
    cur.close()
    conn.close()

def get_all_tickets():
    """ሁሉንም ቲኬቶች ከዳታቤዝ ለማንበብ"""
    conn = get_db_connection()
    cur = conn.cursor()
    # የ 30 ደቂቃ የቆይታ ጊዜ ካለፈ ቲኬቱን መልሶ ክፍት ማድረግ
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
    """የቲኬት መረጃ ለመቀየር"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE tickets SET status = %s, user_id = %s, user_name = %s, expires_at = %s 
        WHERE id = %s
    ''', (status, user_id, user_name, expires_at, ticket_id))
    conn.commit()
    cur.close()
    conn.close()

# --- 4. BOT LOGIC ---

def generate_keyboard():
    tickets = get_all_tickets()
    keyboard = []
    row = []
    for num, data in tickets.items():
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
    try:
        await context.bot.edit_message_text(text, chat_id=GROUP_CHAT_ID, message_id=os.environ.get("GROUP_MSG_ID"), reply_markup=reply_markup, parse_mode="Markdown")
        await context.bot.edit_message_text(text, chat_id=CHANNEL_CHAT_ID, message_id=os.environ.get("CHAN_MSG_ID"), reply_markup=reply_markup, parse_mode="Markdown")
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("select_"):
        ticket_num = int(context.args[0].split("_")[1])
        await handle_selection(update, context, ticket_num)
    else:
        await update.message.reply_text("እንኳን ደህና መጡ! ቲኬት ለመግዛት ግሩፑን ይጎብኙ።")

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_num):
    user = update.effective_user
    tickets = get_all_tickets()
    ticket = tickets[ticket_num]

    if ticket["status"] == "🔴":
        await update.message.reply_text("ይህ ቲኬት ተሽጧል።")
        return
    
    # ቲኬቱን በዳታቤዝ ውስጥ Pending (🟡) ማድረግ
    expiry = datetime.now() + timedelta(minutes=30)
    update_ticket(ticket_num, '🟡', user.id, user.full_name, expiry)
    
    await update.message.reply_text(f"ለቁጥር {ticket_num} ክፍያ በ {TELE_BIRR_NUMBER} ልከው ደረሰኝ እዚህ ይላኩ።")
    await update_live_messages(context)

async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tickets = get_all_tickets()
    ticket_num = next((id for id, d in tickets.items() if d["user_id"] == user.id and d["status"] == "🟡"), None)

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
    content = update.message.reply_to_message.caption or update.message.reply_to_message.text
    target_id = int(content.split("User ID:")[1].split("\n")[0].strip())
    t_num = int(content.split("ቲኬት፡")[1].split("\n")[0].strip())

    if "/approve" in text:
        update_ticket(t_num, '🔴', target_id, content.split("ስም፡")[1].strip(), None)
        await context.bot.send_message(target_id, f"ቲኬት {t_num} ጸድቋል!")
    elif "/reject" in text:
        update_ticket(t_num, '🟢', None, None, None)
        await context.bot.send_message(target_id, "ክፍያዎ ውድቅ ተደርጓል።")
    
    await update_live_messages(context)

# ... (ሌሎች Functions እንደ winner ቀደም ሲል ከነበረው ጋር ተመሳሳይ ናቸው) ...

def main():
    init_db() # ዳታቤዝ ማስጀመር
    keep_alive()
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_CHAT_ID), admin_decision))
    app_bot.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.PHOTO | filters.TEXT), handle_proof))
    app_bot.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(url=f"https://t.me/YOUR_BOT_USERNAME?start={u.callback_query.data}")))
    
    app_bot.run_polling()

if __name__ == '__main__':
    main()
