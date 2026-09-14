import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from app.config import Config

logger = logging.getLogger(__name__)

def admin_only():
    async def func(flt, client: Client, update):
        user = update.from_user
        if not user:
            return False
        return Config.is_authorized(user.id)
    return filters.create(func)

@Client.on_message(~admin_only() & filters.private, group=-1)
async def unauthorized_message_blocker(client: Client, message: Message):
    if message.text and message.text.startswith("/"):
        await message.reply_text("❌ You are not authorized to use this bot.")
    message.stop_propagation()

@Client.on_callback_query(~admin_only(), group=-1)
async def unauthorized_callback_blocker(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("❌ You are not authorized to use this bot.", show_alert=True)
    callback_query.stop_propagation()
