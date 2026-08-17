import re
import time
from typing import Dict
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery
from bot.config import Config
from bot.database.mongo import db

_user_rate_limits: Dict[int, list] = {}
RATE_LIMIT_WINDOW = 10
RATE_LIMIT_MAX = 15

def mask_secret(value: str) -> str:
    if not value or len(value) <= 4:
        return "****"
    if len(value) <= 8:
        return f"{value[:2]}****"
    return f"{value[:3]}****{value[-3:]}"

def mask_env_vars(env_vars: Dict[str, str]) -> Dict[str, str]:
    masked = {}
    secret_keywords = ["key", "token", "secret", "password", "auth", "pwd", "uri", "url", "db"]
    for k, v in env_vars.items():
        is_secret = any(kw in k.lower() for kw in secret_keywords)
        masked[k] = mask_secret(v) if is_secret else v
    return masked

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    user_times = _user_rate_limits.get(user_id, [])
    user_times = [t for t in user_times if now - t < RATE_LIMIT_WINDOW]
    if len(user_times) >= RATE_LIMIT_MAX:
        return True
    user_times.append(now)
    _user_rate_limits[user_id] = user_times
    return False

async def auth_filter_func(_, __, update):
    user = update.from_user
    if not user:
        return False
    if is_rate_limited(user.id):
        return False

    is_auth = await db.is_authorized_user(user.id)
    if not is_auth:
        # If user is not authorized, reply with message if update is a message
        if isinstance(update, Message):
            try:
                await update.reply_text("⛔ <b>Access Denied</b>\n\nYou are not authorized to use this bot.")
            except Exception:
                pass
        elif isinstance(update, CallbackQuery):
            try:
                await update.answer("⛔ Access Denied: Unauthorized user.", show_alert=True)
            except Exception:
                pass
        return False
    return True

auth_filter = filters.create(auth_filter_func)
