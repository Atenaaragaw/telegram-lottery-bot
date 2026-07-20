from datetime import datetime, timedelta
import json
import logging
import os
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- CONFIGURATION ---
BOT_TOKEN = "7805572091:AAGal4nWPVNsItMFa5WpN2KJUQpxYcgEbDs"
ADMIN_CHAT_ID = int("5935470765")
GROUP_CHAT_ID = int("-1004347063089")
CHANNEL_CHAT_ID = int("-1003866567193")
TELE_BIRR_NUMBER = "0912801444"

DATA_FILE = "lottery_data.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def load_data():
    if not os.path.exists(DATA_FILE):
        tickets = {}
        for i in range(1, 51):
            t_num = str(i)
            tickets[t_num] = {
                "status": "open",
                "user_id": None,
                "username": None,
                "pending_time": None,
            }

        default_data = {
            "game_active": False,
            "ticket_price": 100,
            "prize": "5,000 ETB",
            "tickets": tickets,
            "announcement_message_ids": {},
        }
        save_data(default_data)
        return default_data

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    updated = False
    now = datetime.now()
    for t_num, info in data.get("tickets", {}).items():
        if info["status"] == "pending" and info.get("pending_time"):
            try:
                p_time = datetime.fromisoformat(info["pending_time"])
                if now - p_time > timedelta(minutes=30):
                    info["status"] = "open"
                    info["user_id"] = None
                    info["username"] = None
                    info["pending_time"] = None
                    updated = True
            except Exception:
                pass

    if updated:
        save_data(data)

    return data


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def generate_ticket_keyboard(tickets, bot_username=""):
    keyboard = []
    row = []
    status_emojis = {"open": "🟢", "pending": "🟡", "sold": "🔴"}

    for i in range(1, 51):
        t_num = str(i)
        info = tickets.get(t_num, {"status": "open"})
        status = info["status"]
        emoji = status_emojis.get(status, "🟢")

        label = f"{t_num} {emoji}"
        row.append(InlineKeyboardButton(label, callback_data=f"tkt_select_{t_num}"))

        if len(row) == 5:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(
            "🔄 ሰንጠረዥ አድስ (Refresh)", callback_data="refresh_board"
        )
    ])
    return InlineKeyboardMarkup(keyboard)


async def update_live_boards(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    bot_info = await context.bot.get_me()
    keyboard = generate_ticket_keyboard(data["tickets"], bot_info.username)

    open_count = sum(1 for t in data["tickets"].values() if t["status"] == "open")
    pending_count = sum(
        1 for t in data["tickets"].values() if t["status"] == "pending"
    )
    sold_count = sum(1 for t in data["tickets"].values() if t["status"] == "sold")

    sold_details = []
    for t_num, info in data["tickets"].items():
        if info["status"] == "sold":
            uname = f"@{info['username']}" if info.get("username") else f"ID:{info['user_id']}"
            sold_details.append(f"▪️ ቲኬት #{t_num} — {uname} ✅")

    sold_list_text = (
        "\n".join(sold_details) if sold_details else "▪️ ገና የተረጋገጠ የለም"
    )

    board_text = (
        f"🎰 አዲስ ዲጂታል ሎተሪ\n"
        f"የቲኬት ዋጋ፡ {data['ticket_price']} ብር\n"
        f"💰 ሽልማት: {data['prize']}\n\n"
        f"✅ የተረጋገጡ: {sold_count} | ⏳ በመጠባበቅ ላይ: {pending_count} | 🟢 ክፍት: {open_count}\n\n"
        f"✅ የተረጋገጡ ዝርዝር:\n{sold_list_text}\n\n"
        f"👇 ለመግዛት የሚፈልጉትን ቲኬት ይጫኑ:"
    )

    for chat_id_key, msg_id in data.get("announcement_message_ids", {}).items():
        try:
            await context.bot.edit_message_text(
                chat_id=int(chat_id_key),
                message_id=msg_id,
                text=board_text,
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning(f"Could not update message in {chat_id_key}: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()

    bot_info = await context.bot.get_me()
    keyboard = generate_ticket_keyboard(data["tickets"], bot_info.username)
    welcome_text = (
        f"🇪🇹 እንኳን ደህና መጡ ወደ ሎተሪ ቦት!\n\n"
        f"💰 የቲኬት ዋጋ፡ {data['ticket_price']} ብር\n"
        f"🎁 ሽልማት: {data['prize']}\n\n"
        f"ከታች የሚፈልጉትን ቲኬት በመምረጥ መግዛት ይችላሉ:"
    )
    await update.message.reply_text(welcome_text, reply_markup=keyboard)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception:
        pass

    data = load_data()
    user = query.from_user

    if query.data == "refresh_board":
        await update_live_boards(context)
        try:
            await query.answer("ሰንጠረዡ ታድሷል!", show_alert=False)
        except Exception:
            pass
        return

    if query.data.startswith("tkt_select_"):
        t_num = query.data.split("_")[2]
        ticket = data["tickets"].get(t_num)

        if not ticket:
            return

        if ticket["status"] == "sold":
            await query.answer(f"❌ ይቅርታ! ቲኬት ቁጥር {t_num} ቀድሞውኑ ተሽጧል።", show_alert=True)
            return

        if ticket["status"] == "pending":
            if ticket["user_id"] == user.id:
                await query.answer(f"⚠️ ቲኬት ቁጥር {t_num} በእርስዎ ስም ክፍያ በመጠበቅ ላይ ነው።", show_alert=True)
            else:
                await query.answer(f"⚠️ ይቅርታ! ይህ ቲኬት በሌላ ሰው የክፍያ ሂደት ላይ ነው።", show_alert=True)
            return

        data["tickets"][t_num]["status"] = "pending"
        data["tickets"][t_num]["user_id"] = user.id
        data["tickets"][t_num]["username"] = user.username
        data["tickets"][t_num]["pending_time"] = datetime.now().isoformat()
        save_data(data)

        try:
            await update_live_boards(context)
        except Exception as e:
            logger.error(f"Error updating live boards: {e}")

        instructions = (
            f"🎟 መረጡት ቲኬት ቁጥር: {t_num}\n\n"
            f"⚠️ ማሳሰቢያ: ይህ ቲኬት ለሚቀጥሉት 30 ደቂቃዎች ብቻ ለእርስዎ ተይዟል!\n\n"
            f"ትኬቱን ለመግዛት ከታች ያሉትን የቴሌብር መመሪያዎች ይከተሉ:\n\n"
            f"1️⃣ በ TeleBirr ገንዘብ ያስተላልፉ:\n"
            f"   📱 አካውንት ቁጥር: {TELE_BIRR_NUMBER}\n"
            f"   💵 መጠን: {data['ticket_price']} ብር\n\n"
            f"2️⃣ ገንዘቡን ከላኩ በኋላ የግብይቱን ማረጋገጫ በዚህ ፕራይቬት ቻት ፎቶ ወይም ጽሑፍ በመላክ ያረጋግጡ።"
        )
        
        try:
            await context.bot.send_message(chat_id=user.id, text=instructions)
        except Exception as e:
            logger.error(f"Could not send instructions to user {user.id}: {e}")
        return

    if query.data.startswith("tkt_info_"):
        t_num = query.data.split("_")[2]
        ticket = data["tickets"].get(t_num, {})
        status = ticket.get("status", "open")
        if status == "sold":
            await query.answer(f"❌ ቲኬት #{t_num} ተሽጧል!", show_alert=True)
        elif status == "pending":
            await query.answer(f"⚠️ ቲኬት #{t_num} በሂደት ላይ (Pending) ነው።", show_alert=True)
        else:
            await query.answer(f"🟢 ቲኬት #{t_num} ክፍት ነው።", show_alert=True)


async def handle_payment_proof(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if update.message.chat.type != "private":
        return

    user = update.effective_user
    data = load_data()

    pending_ticket = None
    for t_num, info in data["tickets"].items():
        if info["status"] == "pending" and info["user_id"] == user.id:
            pending_ticket = t_num
            break

    if not pending_ticket:
        await update.message.reply_text(
            "ℹ️ በአሁኑ ሰዓት በመጠበቅ ላይ ያለ (Pending) ቲኬት የለዎትም።"
        )
        return

    admin_text = (
        f"📥 አዲስ የክፍያ ማረጋገጫ ደርሷል!\n\n"
        f"🎟 ቲኬት ቁጥር: {pending_ticket}\n"
        f"👤 ስም: {user.full_name}\n"
        f"🆔 ዩዘርናም: @{user.username if user.username else 'N/A'}\n"
        f"🆔 መለያ (ID): {user.id}\n\n"
        f"መልእክት/አይዲ: {update.message.text if update.message.text else '[ፎቶ ማረጋገጫ]'}"
    )

    if update.message.photo:
        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=update.message.photo[-1].file_id,
            caption=admin_text,
        )
    else:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_text,
        )

    await update.message.reply_text(
        f"✅ የቲኬት ቁጥር {pending_ticket} የክፍያ ማረጋገጫዎ ለአስተዳዳሪው ተልኳል! "
        "እባክዎ አስተዳዳሪው እስኪያረጋግጥ ድረስ ትንሽ ይጠብቁ።"
    )


async def admin_action_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ እባክዎ ማረጋገጫውን (Receipt) **Reply** በማድረግ /approve ወይም /reject ይበሉ!")
        return

    replied_msg = update.message.reply_to_message
    replied_text = replied_msg.caption or replied_msg.text or ""

    user_id = None
    t_num = None

    for line in replied_text.split("\n"):
        if "ቲኬት ቁጥር:" in line:
            t_num = line.split("ቲኬት ቁጥር:")[1].strip()
        if "መለያ (ID):" in line:
            try:
                user_id = int(line.split("መለያ (ID):")[1].strip())
            except Exception:
                pass

    if not t_num or not user_id:
        await update.message.reply_text("❌ ከተሰጠው መልእክት ውስጥ የቲኬት ቁጥር ወይም የዩዘር ID ማንበብ አልተቻለም።")
        return

    data = load_data()
    command = update.message.text.lower()

    if "/approve" in command:
        if t_num in data["tickets"]:
            data["tickets"][t_num]["status"] = "sold"
            data["tickets"][t_num]["pending_time"] = None
            save_data(data)
            await update_live_boards(context)

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 እንኳን ደስ አለዎት! የቲኬት ቁጥር {t_num} ክፍያዎ ተረጋግጧል!",
                )
            except Exception as e:
                logger.error(f"Could not message user {user_id}: {e}")

            await update.message.reply_text(f"✅ ቲኬት ቁጥር {t_num} ተረጋግጧል (Sold)!")
            
            try:
                if replied_msg.photo:
                    await replied_msg.edit_caption(caption=f"{replied_text}\n\n✅ ሁኔታ: ጽድቅ ተሰጥቷል (Sold)")
                else:
                    await replied_msg.edit_text(text=f"{replied_text}\n\n✅ ሁኔታ: ጽድቅ ተሰጥቷል (Sold)")
            except Exception:
                pass

    elif "/reject" in command:
        if t_num in data["tickets"]:
            data["tickets"][t_num]["status"] = "open"
            data["tickets"][t_num]["user_id"] = None
            data["tickets"][t_num]["username"] = None
            data["tickets"][t_num]["pending_time"] = None
            save_data(data)
            await update_live_boards(context)

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ ይቅርታ! ለቲኬት ቁጥር {t_num} የላኩት ማረጋገጫ ውድቅ ተደርጓል።",
                )
            except Exception as e:
                logger.error(f"Could not message user {user_id}: {e}")

            await update.message.reply_text(f"❌ ቲኬት ቁጥር {t_num} ውድቅ ተደርጓል (Rejected)።")
            
            try:
                if replied_msg.photo:
                    await replied_msg.edit_caption(caption=f"{replied_text}\n\n❌ ሁኔታ: ውድቅ ተደርጓል (Rejected)")
                else:
                    await replied_msg.edit_text(text=f"{replied_text}\n\n❌ ሁኔታ: ውድቅ ተደርጓል (Rejected)")
            except Exception:
                pass


async def cmd_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    data = load_data()
    data["game_active"] = True

    for t_num in data["tickets"]:
        data["tickets"][t_num] = {
            "status": "open",
            "user_id": None,
            "username": None,
            "pending_time": None,
        }
    save_data(data)

    bot_info = await context.bot.get_me()
    keyboard = generate_ticket_keyboard(data["tickets"], bot_info.username)
    board_text = (
        f"🎰 አዲስ ዲጂታል ሎተሪ\n"
        f"የቲኬት ዋጋ፡ {data['ticket_price']} ብር\n"
        f"💰 ሽልማት: {data['prize']}\n\n"
        f"✅ የተረጋገጡ: 0 | ⏳ በመጠባበቅ ላይ: 0 | 🟢 ክፍት: 50\n\n"
        f"✅ የተረጋገጡ ዝርዝር:\n▪️ ገና የተረጋገጠ የለም\n\n"
        f"👇 ለመግዛት የሚፈልጉትን ቲኬት ይጫኑ:"
    )

    try:
        msg_group = await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=board_text,
            reply_markup=keyboard,
        )
        
        announcement_ids = {str(GROUP_CHAT_ID): msg_group.message_id}
        data["announcement_message_ids"] = announcement_ids
        save_data(data)

        channel_keyboard = [[
            InlineKeyboardButton(
                "🎟 ቲኬት ለመግዛት ግሩፑን ይቀላቀሉ",
                url=f"https://t.me/c/{str(GROUP_CHAT_ID)[4:]}/{msg_group.message_id}"
            )
        ]]
        await context.bot.send_message(
            chat_id=CHANNEL_CHAT_ID,
            text=f"🎰 አዲስ ዲጂታል ሎተሪ ተከፍቷል!\n\n💰 ዋጋ: 100 ብር | 🎁 ሽልማት: 5,000 ብር\n\n👇 ቲኬት ለመምረጥ ግሩፓችንን ይቀላቀሉ!",
            reply_markup=InlineKeyboardMarkup(channel_keyboard),
        )

        await update.message.reply_text("✅ ሎተሪው ተከፍቷል እና ሰንጠረዡ ተዘጋጅቷል!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ መለጠፍ አልተቻለም: {e}")


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    data = load_data()
    data["game_active"] = False
    save_data(data)
    await update.message.reply_text("🔴 ሎተሪው ተዘግቷል!")


async def cmd_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    data = load_data()

    sold_tickets = [
        (t_num, info["user_id"])
        for t_num, info in data["tickets"].items()
        if info["status"] == "sold"
    ]

    if not sold_tickets:
        await update.message.reply_text("❌ የተሸጠ ቲኬት የለም!")
        return

    winner_ticket, winner_id = random.choice(sold_tickets)
    announcement = f"🏆 አሸናፊ ተገኝቷል!\n\n🎟 ቲኬት ቁጥር: {winner_ticket}\n👤 ዩዘር ID: {winner_id}"

    await context.bot.send_message(chat_id=CHANNEL_CHAT_ID, text=announcement)
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=announcement)
    await update.message.reply_text("✅ አሸናፊው ተመርጧል!")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).job_queue(None).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("open", cmd_open))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("winner", cmd_winner))
    app.add_handler(CommandHandler("approve", admin_action_command))
    app.add_handler(CommandHandler("reject", admin_action_command))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_payment_proof))

    print("Bot is running with fully responsive callback buttons...")
    app.run_polling()


if __name__ == "__main__":
    main()
