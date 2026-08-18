import asyncio
import time
import logging
import aiohttp
from typing import Optional, Dict, Any, Tuple
from bot.database.mongo import db

logger = logging.getLogger(__name__)

class UptimeMonitor:
    def __init__(self, bot_client=None, check_interval: int = 10):
        self.bot_client = bot_client
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._previous_status: Dict[str, str] = {}

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info(f"Uptime Kuma style monitor service started (check interval: {self.check_interval}s)")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Uptime monitor service stopped.")

    async def _check_service_url(self, url: str) -> Tuple[bool, int, float]:
        """Performs HTTP GET request to check service health and measure response time."""
        if not url.startswith("http"):
            url = f"https://{url}"

        start_time = time.time()
        headers = {"User-Agent": "RenderDeployerBot-UptimeMonitor/1.0"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=12) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    is_up = resp.status < 500  # <500 considered operational
                    return is_up, resp.status, latency_ms
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                logger.debug(f"Uptime check failed for {url}: {e}")
                return False, 0, latency_ms

    async def check_all_services(self):
        """Checks all registered services and records metrics."""
        deployments = await db.get_all_deployments()
        if not deployments:
            return

        for dep in deployments:
            service_id = dep.get("service_id")
            service_name = dep.get("service_name", "Service")
            user_id = dep.get("user_id")
            service_url = dep.get("service_url")

            if not service_url or not service_id:
                continue

            is_up, status_code, latency_ms = await self._check_service_url(service_url)
            await db.save_uptime_status(service_id, is_up, status_code, latency_ms)

            # Detect state transition (UP <-> DOWN)
            curr_status = "UP" if is_up else "DOWN"
            prev_status = self._previous_status.get(service_id)

            if prev_status and prev_status != curr_status and self.bot_client and user_id:
                if curr_status == "DOWN":
                    msg = (
                        f"🔴 <b>SERVICE DOWN ALERT</b>\n\n"
                        f"<b>Service:</b> {service_name}\n"
                        f"<b>URL:</b> {service_url}\n"
                        f"<b>Status Code:</b> <code>{status_code}</code>\n"
                        f"<b>Response Time:</b> {round(latency_ms, 1)}ms"
                    )
                else:
                    msg = (
                        f"🟢 <b>SERVICE RECOVERED</b>\n\n"
                        f"<b>Service:</b> {service_name}\n"
                        f"<b>URL:</b> {service_url}\n"
                        f"<b>Status Code:</b> <code>{status_code}</code>\n"
                        f"<b>Response Time:</b> {round(latency_ms, 1)}ms"
                    )
                try:
                    await self.bot_client.send_message(user_id, msg)
                except Exception as err:
                    logger.warning(f"Failed to send uptime notification to user {user_id}: {err}")

            self._previous_status[service_id] = curr_status

    async def _monitor_loop(self):
        while self._running:
            try:
                await self.check_all_services()
            except Exception as e:
                logger.error(f"Error in uptime monitor loop: {e}")
            await asyncio.sleep(self.check_interval)
