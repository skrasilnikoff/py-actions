import os
import asyncio
import json
import traceback
from telegram import Bot


async def send_telegram_notification(message: str) -> None:
    """Send a notification message via Telegram bot with extended debugging.

    This function attempts to read `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
    from the environment, falling back to `env_vars.json`. It logs the
    source and a safe preview of values, normalizes `chat_id` types, and
    catches exceptions from the Bot API while printing tracebacks.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    env_source = {"token": "env" if token else None, "chat_id": "env" if chat_id else None}
    fallback_loaded = False

    # Fallback to env_vars.json if not in environment
    if not token or not chat_id:
        try:
            with open("env_vars.json", "r") as f:
                env_vars = json.load(f)
            if not token and env_vars.get("TELEGRAM_TOKEN"):
                token = env_vars.get("TELEGRAM_TOKEN")
                env_source["token"] = "env_vars.json"
            if not chat_id and env_vars.get("TELEGRAM_CHAT_ID"):
                chat_id = env_vars.get("TELEGRAM_CHAT_ID")
                env_source["chat_id"] = "env_vars.json"
            fallback_loaded = True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"DEBUG: env_vars.json not usable: {e}")

    token_preview = (token[:10] + "...") if token else "None"
    chat_preview = (str(chat_id)[:40] + "...") if chat_id else "None"
    print(f"DEBUG: Token: {token_preview}, Chat ID: {chat_preview}, source: {env_source}, fallback_loaded: {fallback_loaded}")

    if not token or not chat_id:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set, skipping Telegram notification")
        return

    # Normalize chat_id to a simple scalar (int or str) if it comes from JSON
    try:
        if isinstance(chat_id, list):
            print("DEBUG: chat_id is a list; using first element")
            chat_id = chat_id[0] if chat_id else None
        elif isinstance(chat_id, dict):
            print("DEBUG: chat_id is a dict; trying common keys")
            for k in ("chat_id", "id", "telegram_chat_id"):
                if k in chat_id:
                    chat_id = chat_id[k]
                    break
            else:
                chat_id = str(chat_id)
        if isinstance(chat_id, bytes):
            chat_id = chat_id.decode("utf-8")
    except Exception as e:
        print(f"DEBUG: Error normalizing chat_id: {e}")
        traceback.print_exc()

    print(f"DEBUG: Final chat_id type={type(chat_id)}, preview={(str(chat_id)[:60] + '...') if chat_id else 'None'}")

    try:
        bot = Bot(token=token)
    except Exception as e:
        print(f"DEBUG: Failed to create Bot: {e}")
        traceback.print_exc()
        return

    try:
        await bot.send_message(chat_id=chat_id, text=message)
        print("DEBUG: Telegram message sent")
    except Exception as e:
        print(f"DEBUG: Failed to send Telegram message: {e}")
        traceback.print_exc()