import logging
import asyncio
from pyrogram import Client, errors
from aiohttp import web
from bot.config import Config
from bot.database.mongo import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def health_check(request):
    return web.Response(text="Bot is running!")

class Bot(Client):
    def __init__(self):
        super().__init__(
            "file_sequencer_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/handlers")
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        logger.info(f"Bot started as @{me.username}")

        # Peer caching logic
        await self.cache_peers()

        # Start Health Check Server
        app = web.Application()
        app.router.add_get("/", health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
        await site.start()
        logger.info(f"Health check server started on port {Config.PORT}")

    async def cache_peers(self):
        """
        Caches essential peers in the local storage to avoid 'Peer ID invalid' errors.
        """
        logger.info("Caching essential peers...")

        # Get channels from config and database
        channels_to_cache = set(Config.REPLACE_TEXT_CHANNELS)
        source_channel = await db.get_source_channel()
        if source_channel:
            channels_to_cache.add(source_channel)

        for chat_id in channels_to_cache:
            # Cache for Bot
            try:
                await self.get_chat(chat_id)
                logger.info(f"Cached chat {chat_id} for Bot")
            except Exception as e:
                logger.warning(f"Bot could not cache chat {chat_id}: {e}")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    bot = Bot()
    bot.run()
