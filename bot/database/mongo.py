from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import Config

class MongoDatabase:
    def __init__(self, uri: str):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client["forward_bot"]

        # Collections
        self.users = self.db["users"]
        self.sessions = self.db["sessions"]
        self.settings = self.db["settings"]
        self.jobs = self.db["jobs"]

db = MongoDatabase(Config.MONGO_URI)
