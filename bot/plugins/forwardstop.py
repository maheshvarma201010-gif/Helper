from pyrogram import Client, filters
from pyrogram.types import Message
from bot.plugins.forward import active_engines
from bot.config import Config

@Client.on_message(filters.command("forwardstop") & filters.private)
async def forwardstop_handler(client: Client, message: Message):
    if message.from_user.id not in Config.ADMINS:
        return

    user_id = message.from_user.id
    if user_id in active_engines:
        active_engines[user_id].stop()
        await message.reply("🛑 Stopping forwarding job... It will finish the current message and stop.")
    else:
        await message.reply("❌ No active forwarding job found for you.")
