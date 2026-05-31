import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")
    MONGO_URI = os.getenv("MONGO_URI")
    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", 0))
    OWNER_ID = int(os.getenv("OWNER_ID", 0))

    if not all([BOT_TOKEN, API_ID, API_HASH, MONGO_URI]):
        print("Warning: Some required environment variables are missing!")
