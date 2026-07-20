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

# --- 1. KEEP-ALIVE ሰርቨር ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running with Advanced Group/Channel Logic!"

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
GROUP_INVITE_LINK = "https://t.me/AddisAllInOneHub" # እዚህ ጋር የግሩፕዎን ሊንክ ይቀይሩ
TELE_BIRR_NUMBER = "0912801444"
TICKET_PRICE = 100
TOTAL_TICKETS = 50

DATABASE_URL = os.environ.get('DATABASE_URL')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 3. ዳታቤዝ ተግባራት ---

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
    cur.execute('''
        UPDATE tickets SET status = '🟢', user_id = NULL, expires_at = NULL 
        WHERE status = '🟡' AND expires_at < %s
    ''', (datetime.now(),))
    conn.commit()
    cur.execute("SELECT id, status, user_id, user_name FROM tickets ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows # List of tuples [(id, status, user_id, user_name), ...]

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

# --- 4. ቦት ተግባራት ---

def generate_grid_keyboard(tickets_data, bot_username):
    keyboard = []
    row = []
    for t_id, status, u_id, u_name in tickets_data:
        url = f"https://t.me/{bot_username}?start=select_{t_id}"
        button_text = f"{t_id} {status}"
        row.append(InlineKeyboardButton(button_text, url=url))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def mask_id(user_id):
    """የተጠቃሚውን ID ለመደበቅ (ለምሳሌ፡ 593****765)"""
    s = str(user_id)
    if len(s) > 4:
        return s[:3] + "****" + s[-3:]
    return "****"

async def update_live_messages(context: ContextTypes.DEFAULT_TYPE):
    tickets_data = get_all_tickets()
    bot_info = await context.bot.get_me()
    
    sold_count = sum(1 for t in tickets_data if t[1] == '🔴')
    pending_count = sum(1 for t in tickets_data if t[1] == '🟡')
    remaining = TOTAL_TICKETS - sold_count

    # --- በግሩፕ ላይ የሚለጠፍ ጽሑፍ ---
    group_text = (
        f"🎰 **የሎተሪ ቲኬቶች ሰሌዳ**\n\n"
        f"📊 **ሁኔታ:** የተሸጡ: {sold_count} | የቀሩ: {remaining}\n"
        f"🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\n"
        f"ቁጥር በመጫን ቲኬት ይግዙ 👇"
    )
    
    # የተሸጡ ዝርዝር
    sold_list = "\n\n📜 **የተሸጡ ቲኬቶች ዝርዝር:**\n"
    has_sold = False
    for t_id, status, u_id, u_name in tickets_data:
        if status == '🔴':
            has_sold = True
            sold_list += f"🎟 ቁጥር {t_id} - {u_name} ({mask_id(u_id)})\n"
    
    if not has_sold: sold_list = ""
    
    final_group_text = group_text + sold_list
    group_markup = generate_grid_keyboard(tickets_data, bot_info.username)

    # --- በቻናል ላይ የሚለጠፍ ጽሑፍ ---
    channel_text = (
        f"🎰 **የሎተሪ ማስታወቂያ**\n\n"
        f"አሁን ላይ {sold_count} ቲኬቶች ተሸጠዋል። {remaining} ቲኬቶች ደግሞ ገና አልተሸጡም!\n\n"
        f"እድልዎን ለመሞከር አሁኑኑ ግሩፑን ይቀላቀሉ 👇"
    )
    channel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ግሩፑን ተቀላቅለህ ግዛ", url=GROUP_INVITE_LINK)]])

    g_msg_id = get_setting("group_msg_id")
    c_msg_id = get_setting("chan_msg_id")

    try:
        if g_msg_id:
            await context.bot.edit_message_text(final_group_text, chat_id=GROUP_CHAT_ID, message_id=int(g_msg_id), reply_markup=group_markup, parse_mode="Markdown")
        if c_msg_id:
            await context.bot.edit_message_text(channel_text, chat_id=CHANNEL_CHAT_ID, message_id=int(c_msg_id), reply_markup=channel_markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Update error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if context.args and context.args[0].startswith("select_"):
        try:
            ticket_num = int(context.args[0].split("_")[1])
            await handle_selection(update, context, ticket_num)
        except: pass
    else:
        await update.message.reply_text(f"ሰላም {user.first_name}! ቲኬት ለመግዛት ግሩፑን ይጎብኙ፡ {GROUP_INVITE_LINK}")

async def open_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    # ዳታቤዙን ሪሴት ማድረግ (አዲስ ዙር ከሆነ)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE tickets SET status='🟢', user_id=NULL, user_name=NULL, expires_at=NULL")
    conn.commit(); cur.close(); conn.close()

    bot_info = await context.bot.get_me()
    
    # መጀመሪያ መልእክቶቹን መላክ
    msg_g = await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="ሰሌዳው እየተዘጋጀ ነው...", parse_mode="Markdown")
    msg_c = await context.bot.send_message(chat_id=CHANNEL_CHAT_ID, text="ማስታወቂያ እየተዘጋጀ ነው...", parse_mode="Markdown")
    
    set_setting("group_msg_id", msg_g.message_id)
    set_setting("chan_msg_id", msg_c.message_id)
    
    await update_live_messages(context)
    await update.message.reply_text("✅ ሎተሪው በግሩፕ እና በቻናል ላይ በይፋ ተከፍቷል።")

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_num):
    user = update.effective_user
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT status, user_id FROM tickets WHERE id = %s", (ticket_num,))
    res = cur.fetchone(); cur.close(); conn.close()
    
    if not res: return
    if res[0] == '🔴':
        await update.message.reply_text("❌ ይቅርታ፣ ይህ ቲኬት ተሽጧል።")
        return
    if res[0] == '🟡' and res[1] != user.id:
        await update.message.reply_text("⚠️ ይህ ቁጥር ሌላ ሰው ሊገዛው ሙከራ ላይ ነው።")
        return

    expiry = datetime.now() + timedelta(minutes=30)
    update_ticket(ticket_num, '🟡', user.id, user.full_name, expiry)
    
    await update.message.reply_text(
        f"✅ ለቁጥር **{ticket_num}** ቲኬት መርጠዋል።\n"
        f"💵 ዋጋ፡ **{TICKET_PRICE} ብር**\n"
        f"📱 ቴሌብር ስልክ፡ `{TELE_BIRR_NUMBER}`\n\n"
        "ደረሰኝ እዚህ ይላኩ። ለ30 ደቂቃ ይቆይልዎታል።", parse_mode="Markdown"
    )
    await update_live_messages(context)

async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tickets_data = get_all_tickets()
    ticket_num = next((t[0] for t in tickets_data if t[2] == user.id and t[1] == '🟡'), None)

    if not ticket_num:
        await update.message.reply_text("ምንም በመጠባበቅ ላይ ያለ ቲኬት የለዎትም።")
        return

    caption = f"📩 ደረሰኝ፡\nቲኬት፡ {ticket_num}\nUser ID: {user.id}\nስም፡ {user.full_name}"
    if update.message.photo:
        await context.bot.send_photo(ADMIN_CHAT_ID, update.message.photo[-1].file_id, caption=caption)
    elif update.message.text:
        await context.bot.send_message(ADMIN_CHAT_ID, f"{caption}\n\nጽሑፍ፡\n{update.message.text}")
    await update.message.reply_text("✅ ማረጋገጫው ለአስተዳዳሪ ተልኳል።")

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID or not update.message.reply_to_message: return
    text = update.message.text.lower()
    content = update.message.reply_to_message.caption or update.message.reply_to_message.text
    if "User ID:" not in content: return
    try:
        uid = int(content.split("User ID:")[1].split("\n")[0].strip())
        tnum = int(content.split("ቲኬት፡")[1].split("\n")[0].strip())
        name = content.split("ስም፡")[1].strip()
    except: return

    if "/approve" in text:
        update_ticket(tnum, '🔴', uid, name, None)
        await context.bot.send_message(uid, f"🎉 እንኳን ደስ አለዎት! ቁጥር {tnum} ጸድቋል።")
    elif "/reject" in text:
        update_ticket(tnum, '🟢', None, None, None)
        await context.bot.send_message(uid, f"❌ ለቁጥር {tnum} የላኩት ክፍያ ውድቅ ሆኗል።")
    
    await update_live_messages(context)

async def pick_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, user_name FROM tickets WHERE status = '🔴'")
    sold = cur.fetchall(); cur.close(); conn.close()
    if not sold: return
    win = random.choice(sold)
    win_text = f"🎊 **የሎተሪው አሸናፊ ታውቋል!** 🎊\n\nዕድለኛ ቁጥር፡ **{win[0]}**\nአሸናፊ፡ **{win[1]}**\n\nእንኳን ደስ አላችሁ! 🎁"
    await context.bot.send_message(GROUP_CHAT_ID, win_text, parse_mode="Markdown")
    await context.bot.send_message(CHANNEL_CHAT_ID, win_text, parse_mode="Markdown")

# --- 5. MAIN ---
def main():
    init_db()
    keep_alive()
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("open", open_lottery))
    app_bot.add_handler(CommandHandler("winner", pick_winner))
    app_bot.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_CHAT_ID), admin_decision))
    application_filter = filters.ChatType.PRIVATE & (filters.PHOTO | filters.TEXT) & ~filters.COMMAND
    app_bot.add_handler(MessageHandler(application_filter, handle_proof))
    app_bot.run_polling()

if __name__ == '__main__':
    main()
