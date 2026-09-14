import logging
from pyrogram import Client
from app.config import Config

logger = logging.getLogger(__name__)

def create_bot() -> Client:
    plugins = dict(root="app/handlers")
    bot = Client(
        "docker_deploy_manager",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins=plugins,
        in_memory=True
    )
    return bot
