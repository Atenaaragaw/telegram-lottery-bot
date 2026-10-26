import os
import logging
import asyncio
import random
import psycopg2
import re
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import (
    BOT_TOKEN, ADMIN_CHAT_ID, GROUP_CHAT_ID, CHANNEL_CHAT_ID,
    GROUP_INVITE_LINK, TELE_BIRR_NUMBER, TICKET_PRICE, TOTAL_TICKETS, DATABASE_URL
)

# --- 1. KEEP-ALIVE ሰርቨር ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot is running with Winner & Repost features!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 3. ዳታቤዝ ተግባራት ---

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY,
                status TEXT DEFAULT '🟢',
                user_id BIGINT,
                user_name TEXT,
                phone_number TEXT,
                expires_at TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS archive_rounds (
                archive_id SERIAL PRIMARY KEY,
                round_date TIMESTAMP,
                ticket_id INTEGER,
                user_id BIGINT,
                user_name TEXT,
                phone_number TEXT
            )
        ''')

        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tickets' AND column_name='phone_number'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE tickets ADD COLUMN phone_number TEXT")

        cur.execute("SELECT COUNT(*) FROM tickets")
        if cur.fetchone()[0] == 0:
            for i in range(1, TOTAL_TICKETS + 1):
                cur.execute("INSERT INTO tickets (id, status) VALUES (%s, %s)", (i, '🟢'))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        if conn: conn.close()

def db_get_all_tickets():
    conn = None
    rows = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            UPDATE tickets SET status = '🟢', user_id = NULL, phone_number = NULL, expires_at = NULL 
            WHERE status = '🟡' AND expires_at < %s
        ''', (datetime.now(),))
        conn.commit()
        cur.execute("SELECT id, status, user_id, user_name, phone_number FROM tickets ORDER BY id")
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        logger.error(f"Error in get_all_tickets: {e}")
    finally:
        if conn: conn.close()
    return rows

def db_update_ticket(ticket_id, status, user_id=None, user_name=None, phone=None, expires_at=None):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            UPDATE tickets SET status = %s, user_id = %s, user_name = %s, phone_number = %s, expires_at = %s 
            WHERE id = %s
        ''', (status, user_id, user_name, phone, expires_at, ticket_id))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error updating ticket {ticket_id}: {e}")
    finally:
        if conn: conn.close()

def db_set_setting(key, value):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, str(value)))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
    finally:
        if conn: conn.close()

def db_get_setting(key):
    conn = None
    val = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        val = row[0] if row else None
        cur.close()
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
    finally:
        if conn: conn.close()
    return val

def archive_and_reset_tickets():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO archive_rounds (round_date, ticket_id, user_id, user_name, phone_number)
            SELECT CURRENT_TIMESTAMP, id, user_id, user_name, phone_number 
            FROM tickets WHERE status = '🔴'
        ''')
        cur.execute("UPDATE tickets SET status='🟢', user_id=NULL, user_name=NULL, phone_number=NULL, expires_at=NULL")
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error archiving and resetting tickets: {e}")
    finally:
        if conn: conn.close()

# --- 4. ቦት ተግባራት ---

def mask_phone(phone):
    if not phone: 
        return "ያልታወቀ"
    p = str(phone).strip()
    if len(p) >= 10:
        return f"{p[:4]}****{p[-2:]}"
    elif len(p) == 9:
        return f"{p[:3]}****{p[-2:]}"
    else:
        return "****"

async def update_live_messages(context: ContextTypes.DEFAULT_TYPE):
    tickets_data = await asyncio.to_thread(db_get_all_tickets)
    bot_info = await context.bot.get_me()
    
    sold_count = sum(1 for t in tickets_data if t[1] == '🔴')
    remaining = TOTAL_TICKETS - sold_count

    deadline_str = await asyncio.to_thread(db_get_setting, "round_deadline")
    deadline_display = "አልተወሰነም"
    if deadline_str:
        try:
            dl_dt = datetime.fromisoformat(deadline_str)
            remaining_time = dl_dt - datetime.now()
            if remaining_time.total_seconds() > 0:
                days = int(remaining_time.total_seconds() // 86400)
                hours = int((remaining_time.total_seconds() % 86400) // 3600)
                minutes = int((remaining_time.total_seconds() % 3600) // 60)
                if days > 0:
                    deadline_display = f"{days} ቀን ከ {hours} ሰዓት"
                else:
                    deadline_display = f"{hours} ሰዓት ከ {minutes} ደቂቃ"
            else:
                deadline_display = "⚠️ የጊዜ ገደቡ አልፏል!"
        except:
            deadline_display = deadline_str

    group_text = (
        f"🔥 **ዕድልዎን የሚፈትኑበት አጓጊ የሎተሪ ሰሌዳ!** 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **የቲኬቶች ሁኔታ:**\n"
        f"የተሸጡ: 🔴 **{sold_count}** | የቀሩ: 🟢 **{remaining}**\n"
        f"⏳ **ዕጣው ሊወጣ የቀረው ጊዜ:** `{deadline_display}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎨 **ሁኔታዎች:** 🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\n"
        f"👇 **አሁኑኑ የሚፈልጉትን ቁጥር በመጫን ዕድልዎን ይሞክሩ!**"
    )
    
    sold_list = "\n\n📜 **የተሸጡ ቲኬቶች ዝርዝር:**\n"
    has_sold = False
    for t_id, status, u_id, u_name, phone in tickets_data:
        if status == '🔴':
            has_sold = True
            sold_list += f"🎟 ቁጥር {t_id} ➔ **{u_name}** (`{mask_phone(phone)}`)\n"
    
    if not has_sold: sold_list = ""
    
    final_group_text = group_text + sold_list
    
    keyboard = []
    row = []
    for t_id, status, u_id, u_name, phone in tickets_data:
        url = f"https://t.me/{bot_info.username}?start=select_{t_id}"
        row.append(InlineKeyboardButton(f"{t_id} {status}", url=url))
        if len(row) == 5:
            keyboard.append(row); row = []
    if row: keyboard.append(row)
    group_markup = InlineKeyboardMarkup(keyboard)

    channel_text = (
        f"🔥 **የአዲስ ሎተሪ ማስታወቂያ!** 🔥\n\n"
        f"📊 የተሸጡ: **{sold_count}** | የቀሩ: **{remaining}**\n"
        f"⏳ ዕጣው ሊወጣ የቀረው ጊዜ: `{deadline_display}`\n\n"
        f"ለመግዛት ግሩፑን ይቀላቀሉ 👇"
    )
    channel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ቲኬት ለመግዛት ግሩፑን ይጎብኙ", url=GROUP_INVITE_LINK)]])

    g_msg_id = await asyncio.to_thread(db_get_setting, "group_msg_id")
    c_msg_id = await asyncio.to_thread(db_get_setting, "chan_msg_id")

    try:
        if g_msg_id: await context.bot.edit_message_text(final_group_text, chat_id=GROUP_CHAT_ID, message_id=int(g_msg_id), reply_markup=group_markup, parse_mode="Markdown")
        if c_msg_id: await context.bot.edit_message_text(channel_text, chat_id=CHANNEL_CHAT_ID, message_id=int(c_msg_id), reply_markup=channel_markup, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Could not edit live messages: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if context.args and context.args[0].startswith("select_"):
        ticket_num = int(context.args[0].split("_")[1])
        await handle_selection(update, context, ticket_num)
    else:
        await update.message.reply_text(f"ሰላም {user.first_name}! ቲኬት ለመግዛት ግሩፑን ይጎብኙ፡ {GROUP_INVITE_LINK}")

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_num):
    user = update.effective_user
    tickets_data = await asyncio.to_thread(db_get_all_tickets)
    ticket = next((t for t in tickets_data if t[0] == ticket_num), None)
    
    if not ticket or ticket[1] == '🔴':
        await update.message.reply_text("❌ ይህ ቲኬት ተሽጧል።")
        return

    expiry = datetime.now() + timedelta(minutes=30)
    await asyncio.to_thread(db_update_ticket, ticket_num, '🟡', user.id, user.full_name, None, expiry)
    
    await update.message.reply_text(
        f"✅ ለቁጥር **{ticket_num}** ቲኬት መርጠዋል።\n\n"
        f"1️⃣ መጀመሪያ የከፈሉበትን የርስዎን**የስልክ ቁጥር** ይላኩ።\n"
        f"2️⃣ በመቀጠል የደረሰኝ ፎቶ ይላኩ።\n\n"
        f"💵 ዋጋ፡ {TICKET_PRICE} ብር | 📱 ቴሌብር፡ `{TELE_BIRR_NUMBER}`", parse_mode="Markdown"
    )
    await update_live_messages(context)

async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tickets_data = await asyncio.to_thread(db_get_all_tickets)
    ticket = next((t for t in tickets_data if t[2] == user.id and t[1] == '🟡'), None)

    if not ticket:
        await update.message.reply_text("ምንም በመጠባበቅ ላይ ያለ ቲኬት የለዎትም።")
        return

    ticket_num = ticket[0]

    if update.message.text and re.match(r"^(09|07|\+2519|\+2517)\d{8}$", update.message.text.strip()):
        phone = update.message.text.strip()
        await asyncio.to_thread(db_update_ticket, ticket_num, '🟡', user.id, user.full_name, phone, ticket[4] if len(ticket)>4 else None)
        await update.message.reply_text(f"✅ ስልክ ቁጥር {phone} ተመዝግቧል። አሁን የደረሰኝ ፎቶ ይላኩ።")
        return

    if update.message.photo or (update.message.text and not re.match(r"^\d+$", update.message.text)):
        saved_phone = ticket[4] if len(ticket) > 4 else "አልተላከም"
        caption = f"📩 አዲስ ደረሰኝ፡\nቲኬት፡ {ticket_num}\nስም፡ {user.full_name}\nየከፈለበት ስልክ፡ {saved_phone}\nUser ID: {user.id}"
        
        if update.message.photo:
            await context.bot.send_photo(ADMIN_CHAT_ID, update.message.photo[-1].file_id, caption=caption)
        else:
            await context.bot.send_message(ADMIN_CHAT_ID, f"{caption}\n\nጽሑፍ፡ {update.message.text}")
        
        await update.message.reply_text("✅ ማረጋገጫው ለአስተዳዳሪ ተልኳል።")

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID or not update.message.reply_to_message: return
    text = update.message.text.lower()
    content = update.message.reply_to_message.caption or update.message.reply_to_message.text
    if "User ID:" not in content: return
    try:
        uid = int(content.split("User ID:")[1].strip())
        tnum = int(content.split("ቲኬት፡")[1].split("\n")[0].strip())
        phone = content.split("የከፈለበት ስልክ፡")[1].split("\n")[0].strip()
        name = content.split("ስም፡")[1].split("\n")[0].strip()
    except Exception as e: 
        logger.error(f"Error parsing admin reply: {e}")
        return

    if "/approve" in text:
        await asyncio.to_thread(db_update_ticket, tnum, '🔴', uid, name, phone, None)
        await context.bot.send_message(uid, f"🎉 ቲኬት {tnum} ጸድቋል መልካም ዕድል!")
        await update.message.reply_text(f"✅ ቁጥር {tnum} ተረጋግጧል።")
    elif "/reject" in text:
        await asyncio.to_thread(db_update_ticket, tnum, '🟢', None, None, None, None)
        await context.bot.send_message(uid, f"❌ ቲኬት {tnum} ውድቅ ሆኗል። እባክዎ እንደገና የኩረጡ!")
        await update.message.reply_text(f"❌ ቁጥር {tnum} ውድቅ ተደርጓል።")
    
    await update_live_messages(context)

async def open_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    await asyncio.to_thread(archive_and_reset_tickets)
    
    default_deadline = datetime.now() + timedelta(days=7)
    await asyncio.to_thread(db_set_setting, "round_deadline", default_deadline.isoformat())

    msg_g = await context.bot.send_message(GROUP_CHAT_ID, "ሰሌዳው እየተዘጋጀ ነው...")
    msg_c = await context.bot.send_message(CHANNEL_CHAT_ID, "ማስታወቂያ...")
    await asyncio.to_thread(db_set_setting, "group_msg_id", msg_g.message_id)
    await asyncio.to_thread(db_set_setting, "chan_msg_id", msg_c.message_id)
    await update_live_messages(context)

async def post_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    # አዲሱን የሰሌዳ መልእክት ወደ ግሩፕ እና ቻናል አዲስ ልኮ አዲሱን ID ማስቀመጥ
    msg_g = await context.bot.send_message(GROUP_CHAT_ID, "ሰሌዳው ይጫናል...")
    msg_c = await context.bot.send_message(CHANNEL_CHAT_ID, "ማስታወቂያ ይጫናል...")
    await asyncio.to_thread(db_set_setting, "group_msg_id", msg_g.message_id)
    await asyncio.to_thread(db_set_setting, "chan_msg_id", msg_c.message_id)
    await update_live_messages(context)
    await update.message.reply_text("✅ አዲሱ ሰሌዳ ግሩፕ ላይ ተለጥፏል! ቦቱ ከእንግዲህ ይህንን አዲስ መልእክት ኤዲት ያደርጋል።")

async def pick_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    tickets_data = await asyncio.to_thread(db_get_all_tickets)
    sold_tickets = [t for t in tickets_data if t[1] == '🔴']
    
    if not sold_tickets:
        await update.message.reply_text("❌ እስካሁን የተሸጠ ቲኬት የለም፣ አሸናፊ መምረጥ አይቻልም!")
        return
    
    # በዘፈቀደ አንድ የተሸጠ ቲኬት መምረጥ
    winner = random.choice(sold_tickets)
    t_id, status, u_id, u_name, phone = winner
    
    winner_text = (
        f"🎉 **እንኳን ደስ አላችሁ! የዕድሉ አሸናፊ ተገኝቷል!** 🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎟 አሸናፊ ቲኬት ቁጥር፡ **{t_id}**\n"
        f"👤 ስም፡ **{u_name}**\n"
        f"📱 ስልክ፡ `{mask_phone(phone)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎊 አሸናፊው በዘፈቀደ ተመርጧል! እንኳን ደስ አለዎት!"
    )
    
    # ለግሩፕ እና ለቻናል ማሳወቅ
    await context.bot.send_message(GROUP_CHAT_ID, winner_text, parse_mode="Markdown")
    try:
        await context.bot.send_message(CHANNEL_CHAT_ID, winner_text, parse_mode="Markdown")
    except:
        pass
    
    await update.message.reply_text(f"✅ አሸናፊው ቁጥር {t_id} ({u_name}) ተመርጦ ለግሩፕ እና ቻናል ተነግሯል!")

async def extend_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    hours_to_add = 24 * 7 
    if context.args:
        try:
            hours_to_add = int(context.args[0])
        except ValueError:
            pass

    current_deadline_str = await asyncio.to_thread(db_get_setting, "round_deadline")
    base_time = datetime.now()
    if current_deadline_str:
        try:
            parsed_dl = datetime.fromisoformat(current_deadline_str)
            if parsed_dl > base_time:
                base_time = parsed_dl 
        except:
            pass

    new_deadline = base_time + timedelta(hours=hours_to_add)
    await asyncio.to_thread(db_set_setting, "round_deadline", new_deadline.isoformat())
    
    days_added = hours_to_add // 24
    await update.message.reply_text(f"✅ የሎተሪው ጊዜ ገደብ በ {days_added} ቀን (ሎች) ተራዝሟል!")
    await update_live_messages(context)

def main():
    init_db()
    keep_alive()
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("open", open_lottery))
    app_bot.add_handler(CommandHandler("post", post_board))
    app_bot.add_handler(CommandHandler("winner", pick_winner))
    app_bot.add_handler(CommandHandler("extend", extend_deadline))
    app_bot.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_CHAT_ID), admin_decision))
    app_bot.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.PHOTO | filters.TEXT) & ~filters.COMMAND, handle_proof))
    
    print("Bot is up and running with /winner and /post commands!")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
