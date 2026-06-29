from pyrogram import Client, filters
from pyrogram.types import Message
from bot.database.mongo import db
from bot.plugins.forward import active_engines
from bot.config import Config

@Client.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    if message.from_user.id not in Config.ADMINS:
        return

    users_count = await db.users.count_documents({})
    sessions_count = await db.sessions.count_documents({})
    active_jobs = len(active_engines)

    stats_text = (
        "📊 **Bot Statistics**\n\n"
        f"👤 **Total Users:** `{users_count}`\n"
        f"🔑 **Logged-in Admins:** `{sessions_count}`\n"
        f"🚀 **Active Forwarding Jobs:** `{active_jobs}`"
    )
    await message.reply(stats_text)
