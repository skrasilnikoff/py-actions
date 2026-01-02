import os
import asyncio
import json
from telegram import Bot

async def send_telegram_notification(message: str) -> None:
    """Send a notification message via Telegram bot."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Fallback to env_vars.json if not in environment
    if not token or not chat_id:
        try:
            with open("env_vars.json", "r") as f:
                env_vars = json.load(f)
            token = token or env_vars.get("TELEGRAM_TOKEN")
            chat_id = chat_id or env_vars.get("TELEGRAM_CHAT_ID")
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    token_preview = (token[:10] + '...') if token else 'None'
    chat_id_preview = (str(chat_id)[:10] + '...') if chat_id else 'None'
    print(f"DEBUG: Token: {token_preview}, Chat ID: {chat_id_preview}")
    if not token or not chat_id:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set, skipping Telegram notification")
        return
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message)
    print("DEBUG: Telegram message sent")