import os
import logging
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/render_deployer")
    PORT = int(os.getenv("PORT", "8080"))

    # Comma-separated list of Telegram user IDs allowed to use the bot
    _admin_ids_raw = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]

    # Optional default Render API Key if provided by host
    RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")

    # Secret key used for local encryption of stored Render API keys
    ENCRYPTION_SECRET = os.getenv("ENCRYPTION_SECRET", "default_render_deployer_secret_key_32bytes!")

    @classmethod
    def validate(cls):
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.MONGO_URI:
            missing.append("MONGO_URI")

        if missing:
            logging.warning(f"Missing recommended environment variables: {', '.join(missing)}")
