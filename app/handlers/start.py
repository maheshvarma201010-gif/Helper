from pyrogram import Client, filters
from pyrogram.types import Message
from app.config import Config

START_TEXT = (
    "👋 Welcome to Docker Deploy Manager\n\n"
    "🐳 Manage and deploy Docker projects directly from Telegram.\n\n"
    "Available commands:\n\n"
    "/deploy - Deploy a new project\n"
    "/status - Show all projects\n"
    "/logs - View project logs\n"
    "/restart - Restart a project\n"
    "/pause - Pause a project\n"
    "/stop - Stop a project\n"
    "/startproject - Start a stopped project\n"
    "/replace - Replace project ZIP\n"
    "/env - Upload/update project .env\n"
    "/redeploy - Redeploy a project\n"
    "/remove - Remove a project\n\n"
    "Only authorized administrators can manage projects."
)

UNAUTHORIZED_TEXT = "❌ You are not authorized to use this bot."

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text(UNAUTHORIZED_TEXT)
        return
    await message.reply_text(START_TEXT)
