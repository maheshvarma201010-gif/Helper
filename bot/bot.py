import logging
import asyncio
from pyrogram import Client, errors
from aiohttp import web
from bot.config import Config
from bot.database.mongo import db
from bot.web.server import create_web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class RenderDeployerBot(Client):
    def __init__(self):
        super().__init__(
            "render_deployer_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/handlers")
        )

    async def start(self):
        Config.validate()
        db.connect()
        await super().start()
        me = await self.get_me()
        logger.info(f"Render Deployer Bot started as @{me.username}")

        from pyrogram.types import BotCommand
        await self.set_bot_commands([
            BotCommand("start", "Show welcome menu"),
            BotCommand("create_repo", "Import or create a repository"),
            BotCommand("zip", "Deploy project from .zip archive"),
            BotCommand("deploy", "Start a new deployment"),
            BotCommand("projects", "List connected Render services"),
            BotCommand("status", "Show status of services"),
            BotCommand("logs", "Fetch recent deployment logs"),
            BotCommand("restart", "Restart a service"),
            BotCommand("redeploy", "Trigger a new deployment"),
            BotCommand("stop", "Suspend a service"),
            BotCommand("delete", "Delete a service"),
            BotCommand("env", "View and manage environment variables"),
            BotCommand("env_converter", "Convert config files to .env format"),
            BotCommand("settings", "Configure Render API key"),
            BotCommand("help", "Show command documentation")
        ])

        # Start Health Check Server
        app = create_web_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
        await site.start()
        logger.info(f"Health check web server running on port {Config.PORT}")

    async def stop(self, *args):
        await super().stop()
        logger.info("Render Deployer Bot stopped.")

if __name__ == "__main__":
    bot = RenderDeployerBot()
    bot.run()
