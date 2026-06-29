import base64
from typing import Optional
from cryptography.fernet import Fernet
from bot.database.mongo import db
from bot.config import Config

def get_fernet():
    key = Config.SESSION_ENCRYPTION_KEY
    if len(key) < 32:
        key = key.ljust(32, "0")
    fernet_key = base64.urlsafe_b64encode(key[:32].encode())
    return Fernet(fernet_key)

async def save_session(user_id: int, session_string: str):
    fernet = get_fernet()
    encrypted_session = fernet.encrypt(session_string.encode()).decode()
    await db.sessions.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": encrypted_session}},
        upsert=True
    )

async def get_session(user_id: int) -> Optional[str]:
    data = await db.sessions.find_one({"user_id": user_id})
    if not data:
        return None

    encrypted_session = data["session_string"]
    try:
        fernet = get_fernet()
        return fernet.decrypt(encrypted_session.encode()).decode()
    except Exception:
        return encrypted_session # Fallback if not encrypted or key changed

async def delete_session(user_id: int):
    await db.sessions.delete_one({"user_id": user_id})

async def get_all_sessions():
    return await db.sessions.find().to_list(length=None)
