from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import Config

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(Config.MONGO_URI)
        self.db = self.client["telegram_bot"]
        self.users = self.db["users"]
        self.sessions = self.db["sessions"]
        self.jobs = self.db["jobs"]
        self.sequences = self.db["sequences"]
        self.replace_jobs = self.db["replace_jobs"]

    async def get_user(self, user_id):
        return await self.users.find_one({"user_id": user_id})

    async def add_user(self, user_id, first_name):
        if not await self.get_user(user_id):
            await self.users.insert_one({"user_id": user_id, "first_name": first_name})

    async def update_user_state(self, user_id, state):
        await self.users.update_one({"user_id": user_id}, {"$set": {"state": state}}, upsert=True)

    async def get_user_state(self, user_id):
        user = await self.users.find_one({"user_id": user_id})
        return user.get("state") if user else None

    # Sequence Job Methods
    async def add_sequence_file(self, user_id, file_data):
        await self.sequences.update_one(
            {"user_id": user_id},
            {"$push": {"files": file_data}},
            upsert=True
        )

    async def get_sequence_files(self, user_id):
        job = await self.sequences.find_one({"user_id": user_id})
        return job.get("files", []) if job else []

    async def clear_sequence_files(self, user_id):
        await self.sequences.delete_one({"user_id": user_id})

    # Replace Job Methods
    async def update_replace_data(self, user_id, data):
        await self.replace_jobs.update_one(
            {"user_id": user_id},
            {"$set": data},
            upsert=True
        )

    async def get_replace_data(self, user_id):
        return await self.replace_jobs.find_one({"user_id": user_id})

    async def clear_replace_data(self, user_id):
        await self.replace_jobs.delete_one({"user_id": user_id})

db = Database()
