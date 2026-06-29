from bot.database.mongo import db

async def set_setting(key: str, value: any):
    await db.settings.update_one(
        {"key": key},
        {"$set": {"value": value}},
        upsert=True
    )

async def get_setting(key: str, default=None):
    data = await db.settings.find_one({"key": key})
    return data["value"] if data else default
