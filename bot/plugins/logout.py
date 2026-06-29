from pyrogram import Client, filters
from pyrogram.types import Message
from bot.database.sessions import delete_session
from bot.core.client import client_manager
from bot.config import Config

@Client.on_message(filters.command("logout") & filters.private)
async def logout_handler(client: Client, message: Message):
    if message.from_user.id not in Config.ADMINS:
        return

    user_id = message.from_user.id
    await delete_session(user_id)
    await client_manager.stop_user_client(user_id)

    await message.reply("👋 Logged out successfully. Session removed.")
