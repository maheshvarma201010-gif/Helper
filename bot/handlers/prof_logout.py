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

    # Stop all active professional jobs
    active_jobs = await db.prof_forward_jobs.find({"user_id": user_id, "status": "running"}).to_list(length=None)
    for job in active_jobs:
        await db.update_prof_forward_job(job["job_id"], {"status": "stopped"})
        # active_prof_tasks cleanup is handled in worker finally block or by cancel
        # but here we can just stop the client which will stop workers.

    await db.delete_admin_session()

    # If the bot has an active admin_userbot client, stop it
    if hasattr(client, "admin_userbot") and client.admin_userbot:
        try:
            await client.admin_userbot.stop()
            client.admin_userbot = None
            logger.info(f"Admin {user_id} logged out. Userbot stopped.")
        except Exception as e:
            logger.error(f"Error stopping admin userbot for {user_id}: {e}")

    await message.reply_text("✅ **Logged out successfully.**\nAll active jobs stopped and session deleted.")
