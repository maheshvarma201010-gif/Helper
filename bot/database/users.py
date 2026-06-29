from typing import Optional, Any, Dict
from bot.database.mongo import db

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    return await db.users.find_one({"user_id": user_id})

async def add_user(user_id: int, first_name: str):
    if not await get_user(user_id):
        await db.users.insert_one({
            "user_id": user_id,
            "first_name": first_name,
            "joined_at": None, # Could add datetime
            "state": None
        })

async def set_user_state(user_id: int, state: Optional[str], data: Optional[Dict] = None):
    update = {"$set": {"state": state}}
    if data is not None:
        update["$set"]["data"] = data
    else:
        update["$unset"] = {"data": ""}
    await db.users.update_one({"user_id": user_id}, update, upsert=True)

async def get_user_state(user_id: int) -> Optional[Dict]:
    user = await get_user(user_id)
    if user:
        return {"state": user.get("state"), "data": user.get("data", {})}
    return None
