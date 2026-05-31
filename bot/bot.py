import logging
import asyncio
from pyrogram import Client
from aiohttp import web
from bot.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def health_check(request):
    return web.Response(text="Bot and Userbot are running!")

class Bot(Client):
    def __init__(self):
        super().__init__(
            "file_sequencer_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/handlers")
        )

        # Userbot (String Session) initialization
        self.userbot = Client(
            "userbot_session",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=Config.STRING_SESSION
        )

    async def start(self):
        await super().start()
        await self.userbot.start()

        me = await self.get_me()
        user_me = await self.userbot.get_me()
        logger.info(f"Bot started as @{me.username}")
        logger.info(f"Userbot started as {user_me.first_name} (@{user_me.username or 'NoUsername'})")

        # Start Health Check Server
        app = web.Application()
        app.router.add_get("/", health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
        await site.start()
        logger.info(f"Health check server started on port {Config.PORT}")

    async def stop(self, *args):
        await super().stop()
        await self.userbot.stop()
        logger.info("Bot and Userbot stopped.")

if __name__ == "__main__":
    bot = Bot()
    bot.run()
