import asyncio
import logging
from typing import Optional
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.render_api import RenderAPI

logger = logging.getLogger(__name__)

class FreeTierLimitNotifier:
    def __init__(self, bot_client=None, check_interval: int = 3600):
        self.bot_client = bot_client
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._notifier_loop())
            logger.info(f"FreeTierLimitNotifier started (check interval: {self.check_interval}s)")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("FreeTierLimitNotifier stopped.")

    async def check_and_notify_users(self):
        """Queries users and sends hourly reminder if free plan or bandwidth limit is nearing/exceeded."""
        users = await db.get_all_users()
        if not users:
            return

        for user_doc in users:
            user_id = user_doc.get("user_id")
            if not user_id or not self.bot_client:
                continue

            api_key = await db.get_user_render_key(user_id)
            if not api_key:
                continue

            try:
                render = RenderAPI(api_key)
                services = await render.list_services()
                if not services:
                    continue

                # Check if any service is on free tier or suspended/approaching limits
                has_free_services = False
                for item in services:
                    srv = item.get("service", item)
                    details = srv.get("serviceDetails", {})
                    plan = details.get("plan", "free")
                    status = srv.get("suspended", "not_suspended")
                    if plan == "free" or status in ["suspended", "suspended_limit"]:
                        has_free_services = True
                        break

                if has_free_services:
                    msg_text = (
                        "⚠️ <b>Render Free Tier / Bandwidth Expiry Reminder</b>\n\n"
                        "Your Render free tier instance hours or monthly bandwidth limits may be expiring soon or reached.\n\n"
                        "💡 <b>Action Required:</b> Please update your Render API Key in /settings with a new Render account "
                        "to migrate and keep all your services running 24/7 without interruption!"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔑 Update Render API Key", callback_data="update_api_key")],
                        [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
                    ])

                    try:
                        await self.bot_client.send_message(user_id, msg_text, reply_markup=kb)
                        logger.info(f"Sent hourly free tier expiry reminder to user {user_id}")
                    except Exception as err_msg:
                        logger.warning(f"Failed to send hourly limit notification to {user_id}: {err_msg}")

            except Exception as e:
                logger.warning(f"Error checking free tier status for user {user_id}: {e}")

    async def _notifier_loop(self):
        while self._running:
            try:
                await self.check_and_notify_users()
            except Exception as e:
                logger.error(f"Error in limit notifier loop: {e}")
            await asyncio.sleep(self.check_interval)
