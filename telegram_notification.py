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

    # Normalize chat_id into a list of ids (support comma-separated string)
    def _parse_chat_ids(raw):
        ids = []
        try:
            if raw is None:
                return []
            # bytes -> str
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            # If it's already a list, use it
            if isinstance(raw, list):
                ids = raw
            # If it's a dict, try common keys
            elif isinstance(raw, dict):
                for k in ("chat_id", "id", "telegram_chat_id"):
                    if k in raw:
                        ids = [raw[k]]
                        break
                else:
                    ids = [str(raw)]
            else:
                # Treat as string and split by comma
                raw_str = str(raw)
                parts = [p.strip() for p in raw_str.split(",") if p.strip()]
                ids = parts
        except Exception as e:
            print(f"DEBUG: Error parsing chat ids: {e}")
            traceback.print_exc()
        # Normalize each id to int when possible
        norm = []
        for item in ids:
            try:
                norm.append(int(item))
            except Exception:
                norm.append(item)
        return norm

    chat_ids = _parse_chat_ids(chat_id)
    print(f"DEBUG: Final chat_ids={chat_ids}")

    try:
        bot = Bot(token=token)
    except Exception as e:
        print(f"DEBUG: Failed to create Bot: {e}")
        traceback.print_exc()
        return

    # Send to each chat id
    for cid in chat_ids:
        try:
            await bot.send_message(chat_id=cid, text=message)
            print(f"DEBUG: Telegram message sent to {cid}")
        except Exception as e:
            print(f"DEBUG: Failed to send Telegram message to {cid}: {e}")
            traceback.print_exc()