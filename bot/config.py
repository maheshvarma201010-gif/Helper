import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")
    MONGO_URI = os.getenv("MONGO_URI")
    OWNER_ID = int(os.getenv("OWNER_ID", 0))
    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", 0))
    PORT = int(os.getenv("PORT", 8080))
    BASE_URL = os.getenv("BASE_URL", os.getenv("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}"))

    # Admins list
    raw_admins = os.getenv("ADMINS", "")
    ADMINS = [int(i.strip()) for i in raw_admins.split(",") if i.strip().isdigit()]
    if OWNER_ID and OWNER_ID not in ADMINS:
        ADMINS.append(OWNER_ID)

    # Authorized channels for replacement
    raw_channels = os.getenv("REPLACE_TEXT_CHANNELS", "")
    REPLACE_TEXT_CHANNELS = [int(i.strip()) for i in raw_channels.split(",") if i.strip().lstrip('-').isdigit()]

    if not all([BOT_TOKEN, API_ID, API_HASH, MONGO_URI]):
        print("Warning: Some required environment variables are missing!")
