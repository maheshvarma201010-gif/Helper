import logging
from pyrogram import Client, filters
from bot.config import Config
from bot.database.mongo import db

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("logout") & filters.user(Config.ADMINS) & filters.private, group=-2)
async def logout_command(client, message):
    message.stop_propagation()
    user_id = message.from_user.id

    session = await db.get_admin_session()
    if not session:
        return await message.reply_text("❌ You are not logged in.")

    await db.delete_admin_session()

    # If the bot has an active admin_userbot client, stop it
    if hasattr(client, "admin_userbot") and client.admin_userbot:
        try:
            await client.admin_userbot.stop()
            client.admin_userbot = None
            logger.info("Admin userbot stopped and cleared.")
        except Exception as e:
            logger.error(f"Error stopping admin userbot: {e}")

    await message.reply_text("✅ **Logged out successfully.**\nSession deleted from database.")
