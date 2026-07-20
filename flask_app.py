import asyncio
from flask import Flask, request
from telegram import Update
from bot import get_bot_application

app = Flask(__name__)

# Initialize the Telegram bot application asynchronously
telegram_app = get_bot_application()
loop = asyncio.get_event_loop()
loop.run_until_complete(telegram_app.initialize())

@app.route("/")
def home():
    return "Lottery Bot Webhook is running 24/7 on Render!"

@app.route(f"/{telegram_app.bot.token}", methods=["POST"])
def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, telegram_app.bot)
    
    # Process update asynchronously via Flask request context
    async def process():
        await telegram_app.process_update(update)

    loop.run_until_complete(process())
    return "OK", 200
