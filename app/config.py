import os
import logging
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID: int = int(os.getenv("API_ID", "0")) if os.getenv("API_ID", "0").isdigit() else 0
    API_HASH: str = os.getenv("API_HASH", "")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    _admin_ids_raw = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS: list[int] = [
        int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()
    ]

    _owner_id_raw = os.getenv("OWNER_ID", "0")
    OWNER_ID: int = int(_owner_id_raw.strip()) if _owner_id_raw.strip().isdigit() else 0

    BASE_URL: str = os.getenv("BASE_URL", "")
    MONGODB_URL: str = os.getenv("MONGODB_URL", "")

    @classmethod
    def is_authorized(cls, user_id: int) -> bool:
        if not user_id:
            return False
        if cls.OWNER_ID and user_id == cls.OWNER_ID:
            return True
        if user_id in cls.ADMIN_IDS:
            return True
        return False

    @classmethod
    def validate(cls) -> list[str]:
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.OWNER_ID:
            missing.append("OWNER_ID")
        if not cls.MONGODB_URL:
            missing.append("MONGODB_URL")
        return missing
