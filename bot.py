import os
import logging
import asyncio
import random
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask

# Telegram libraries
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- 1. ለ Render KEEP-ALIVE ሰርቨር (Flask) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    # Render የሚሰጠውን PORT ይጠቀማል፣ ካልተገኘ 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. የቦቱ ማዋቀሪያ (CONFIG) ---
BOT_TOKEN = "7805572091:AAGal4nWPVNsItMFa5WpN2KJUQpxYcgEbDs"
ADMIN_CHAT_ID = 5935470765
GROUP_CHAT_ID = -1004347063089
CHANNEL_CHAT_ID = -1003866567193
TELE_BIRR_NUMBER = "0912801444"
TICKET_PRICE = 100
TOTAL_TICKETS = 50

# የቲኬቶች ዳታቤዝ (በሜሞሪ ላይ)
# ማሳሰቢያ፡ ቦቱ Restart ሲያደርግ ይህ መረጃ ይጠፋል
tickets = {i: {"status": "🟢", "user_id": None, "user_name": "", "expires_at": None} for i in range(1, TOTAL_TICKETS + 1)}
message_trackers = {"group_msg_id": None, "channel_msg_id": None}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 3. ረዳት ተግባራት (HELPER FUNCTIONS) ---

def generate_keyboard():
    """የቲኬቶቹን ሰንጠረዥ ይፈጥራል"""
    keyboard = []
    row = []
    now = datetime.now()

    for num, data in tickets.items():
        # የ30 ደቂቃ የቆይታ ጊዜ ካለፈ ቲኬቱን መልሶ ክፍት ማድረግ
        if data["status"] == "🟡" and data["expires_at"] and now > data["expires_at"]:
            data["status"] = "🟢"
            data["user_id"] = None
            data["expires_at"] = None

        status_icon = data["status"]
        button_text = f"{num} {status_icon}"
        callback_data = f"select_{num}"
        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        
        if len(row) == 5:
            keyboard.append(row)
            row = []
    
    if row: keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def update_live_messages(context: ContextTypes.DEFAULT_TYPE):
    """በግሩፕ እና በቻናል ላይ ያለውን ሰንጠረዥ ያድሳል"""
    text = (
        "🎰 **የሎተሪ ቲኬቶች ዝርዝር**\n\n"
        "🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\n"
        "**የአንዱ ቲኬት ዋጋ፡ 100 ብር**\n"
        "ለመግዛት የፈለጉትን ቁጥር ይጫኑ።"
    )
    reply_markup = generate_keyboard()
    
    try:
        if message_trackers["group_msg_id"]:
            await context.bot.edit_message_text(
                text=text, chat_id=GROUP_CHAT_ID, 
                message_id=message_trackers["group_msg_id"], 
                reply_markup=reply_markup, parse_mode="Markdown"
            )
        if message_trackers["channel_msg_id"]:
            await context.bot.edit_message_text(
                text=text, chat_id=CHANNEL_CHAT_ID, 
                message_id=message_trackers["channel_msg_id"], 
                reply_markup=reply_markup, parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"Update Error: {e}")

# --- 4. የቦቱ ትዕዛዞች (HANDLERS) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    # Deep-link handle: /start select_5
    if args and args[0].startswith("select_"):
        try:
            ticket_num = int(args[0].split("_")[1])
            await handle_selection_logic(update, context, ticket_num)
        except:
            await update.message.reply_text("ስህተት ተከስቷል። እባክዎ እንደገና ይሞክሩ።")
    else:
        await update.message.reply_text(
            f"ሰላም {user.first_name}! እንኳን ወደ ሎተሪ ቦት በሰላም መጡ።\n\n"
            "ቲኬት ለመግዛት በግሩፕ ወይም በቻናል የተለጠፈውን ሰንጠረዥ ይጠቀሙ።"
        )

async def open_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """አስተዳዳሪው ሎተሪውን እንዲከፍት"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    text = "🎰 **የሎተሪ ቲኬቶች ዝርዝር ተከፍቷል!**\n\n🟢 ክፍት | 🟡 በመጠባበቅ | 🔴 የተሸጠ\n\nለመግዛት ቁጥር ይጫኑ።"
    reply_markup = generate_keyboard()
    
    msg_g = await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    msg_c = await context.bot.send_message(chat_id=CHANNEL_CHAT_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    
    message_trackers["group_msg_id"] = msg_g.message_id
    message_trackers["channel_msg_id"] = msg_c.message_id
    await update.message.reply_text("✅ ሎተሪው በግሩፕ እና በቻናል ላይ በይፋ ተከፍቷል።")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """በግሩፕ ውስጥ ቁጥር ሲጫኑ ወደ ቦቱ ፕራይቬት ቻት የሚወስድ"""
    query = update.callback_query
    ticket_num = query.data.split("_")[1]
    bot_info = await context.bot.get_me()
    # Redirect with deep link
    url = f"https://t.me/{bot_info.username}?start=select_{ticket_num}"
    await query.answer(url=url)

async def handle_selection_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_num: int):
    user = update.effective_user
    ticket = tickets.get(ticket_num)

    if not ticket: return

    if ticket["status"] == "🔴":
        await update.message.reply_text("❌ ይቅርታ፣ ይህ ቲኬት ቀደም ብሎ ተሽጧል። እባክዎ ሌላ ይምረጡ።")
        return
    
    if ticket["status"] == "🟡" and ticket["user_id"] != user.id:
        await update.message.reply_text("⚠️ ይህ ቲኬት ሌላ ሰው ለመግዛት ሙከራ እያደረገ ነው (Pending)።")
        return

    # ቲኬቱን ለጊዜው መያዝ (30 ደቂቃ)
    ticket["status"] = "🟡"
    ticket["user_id"] = user.id
    ticket["user_name"] = user.full_name
    ticket["expires_at"] = datetime.now() + timedelta(minutes=30)

    payment_msg = (
        f"✅ ለቁጥር **{ticket_num}** ቲኬት መርጠዋል።\n\n"
        f"💵 ዋጋ፡ **{TICKET_PRICE} ብር**\n"
        f"📱 የቴሌብር ቁጥር፡ `{TELE_BIRR_NUMBER}`\n\n"
        "እባክዎ ክፍያውን ፈጽመው የደረሰኝ ፎቶ (Screenshot) እዚህ ይላኩ።\n"
        "⚠️ ይህ ቲኬት ለ 30 ደቂቃ ብቻ ይጠበቅልዎታል።"
    )
    await update.message.reply_text(payment_msg, parse_mode="Markdown")
    await update_live_messages(context)

async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ተጠቃሚው ደረሰኝ ሲልክ ለአስተዳዳሪው ያስተላልፋል"""
    user = update.effective_user
    
    # ተጠቃሚው የያዘውን ቲኬት መፈለግ
    user_ticket = next((num for num, data in tickets.items() if data["user_id"] == user.id and data["status"] == "🟡"), None)
    
    if not user_ticket:
        await update.message.reply_text("ምንም በመጠባበቅ ላይ ያለ ቲኬት የለዎትም። መጀመሪያ ቁጥር ይምረጡ።")
        return

    caption = (
        f"📩 **የክፍያ ማረጋገጫ ደርሷል**\n\n"
        f"ከ፡ {user.full_name} (@{user.username})\n"
        f"ቲኬት ቁጥር፡ {user_ticket}\n"
        f"User ID: {user.id}"
    )
    
    if update.message.photo:
        await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=update.message.photo[-1].file_id, caption=caption)
    elif update.message.text:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"{caption}\n\nጽሑፍ ማረጋገጫ፡\n{update.message.text}")
    
    await update.message.reply_text("✅ ማረጋገጫው ለአስተዳዳሪ ተልኳል። ሲረጋገጥ መልእክት ይደርስዎታል።")

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """አስተዳዳሪው ሲያጸድቅ ወይም ውድቅ ሲያደርግ"""
    if update.effective_user.id != ADMIN_CHAT_ID or not update.message.reply_to_message:
        return

    msg_text = update.message.text.lower()
    reply_msg = update.message.reply_to_message
    content = reply_msg.caption or reply_msg.text

    if "User ID:" not in content: return

    try:
        target_user_id = int(content.split("User ID:")[1].strip())
        ticket_num = int(content.split("ቲኬት ቁጥር:")[1].split("\n")[0].strip())
    except:
        await update.message.reply_text("ስህተት፡ መረጃውን ማንበብ አልተቻለም።")
        return

    if "/approve" in msg_text:
        tickets[ticket_num]["status"] = "🔴"
        tickets[ticket_num]["expires_at"] = None
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 እንኳን ደስ አለዎት! ለቁጥር {ticket_num} የከፈሉት ክፍያ ተረጋግጦ ቲኬቱ የእርስዎ ሆኗል። መልካም እድል!")
        await update.message.reply_text(f"✅ ቲኬት {ticket_num} ተረጋገጠ።")
    elif "/reject" in msg_text:
        tickets[ticket_num]["status"] = "🟢"
        tickets[ticket_num]["user_id"] = None
        await context.bot.send_message(chat_id=target_user_id, text=f"❌ ይቅርታ፣ ለቁጥር {ticket_num} የላኩት ማረጋገጫ ተቀባይነት አላገኘም።")
        await update.message.reply_text(f"❌ ቲኬት {ticket_num} ውድቅ ተደርጓል።")
    
    await update_live_messages(context)

async def pick_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """አሸናፊ በዘፈቀደ ለመምረጥ"""
    if update.effective_user.id != ADMIN_CHAT_ID: return
    
    sold_tickets = [num for num, data in tickets.items() if data["status"] == "🔴"]
    
    if not sold_tickets:
        await update.message.reply_text("ምንም የተሸጠ ቲኬት የለም።")
        return
    
    winner_num = random.choice(sold_tickets)
    winner_data = tickets[winner_num]
    
    winner_text = (
        f"🎊 **የሎተሪው አሸናፊ ታውቋል!** 🎊\n\n"
        f"ዕድለኛ ቁጥር፡ **{winner_num}**\n"
        f"አሸናፊ፡ **{winner_data['user_name']}**\n\n"
        "እንኳን ደስ አላችሁ! 🎁"
    )
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=winner_text, parse_mode="Markdown")
    await context.bot.send_message(chat_id=CHANNEL_CHAT_ID, text=winner_text, parse_mode="Markdown")
    await update.message.reply_text(f"አሸናፊው ተለይቷል፡ ቁጥር {winner_num}")

# --- 5. MAIN ---

def main():
    # 24/7 ሰርቨሩን ማስጀመር
    keep_alive()

    # ቦቱን ማስጀመር
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("open", open_lottery))
    application.add_handler(CommandHandler("winner", pick_winner))
    application.add_handler(CommandHandler("approve", admin_decision))
    application.add_handler(CommandHandler("reject", admin_decision))
    
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # ክፍያ ለሚልኩ (Photo ወይም Text)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.PHOTO | filters.TEXT) & ~filters.COMMAND, handle_proof))

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
