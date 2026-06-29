import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]
    PORT = int(os.getenv("PORT", 8080))

    # Session encryption key (optional but recommended)
    SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY", "super-secret-key")
