import logging
from datetime import datetime, timezone
from typing import Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import Config

logger = logging.getLogger(__name__)

class Database:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect(cls):
        if not Config.MONGODB_URL:
            logger.warning("MONGODB_URL is not set. Database operations will fail unless configured.")
            return
        try:
            cls.client = AsyncIOMotorClient(Config.MONGODB_URL)
            cls.db = cls.client.get_default_database()
            if cls.db is None:
                # If URL didn't specify db name, default to 'deploy_manager'
                cls.db = cls.client["deploy_manager"]
            logger.info("Connected to MongoDB successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed.")

    @classmethod
    def get_projects_collection(cls):
        if cls.db is None:
            raise RuntimeError("Database connection is not initialized.")
        return cls.db["projects"]

    @classmethod
    async def create_project(cls, project_data: dict[str, Any]) -> dict[str, Any]:
        collection = cls.get_projects_collection()
        now = datetime.now(timezone.utc).isoformat()
        project_data.setdefault("created_at", now)
        project_data.setdefault("updated_at", now)
        project_data.setdefault("last_error", None)
        project_data.setdefault("env_vars", {})
        await collection.insert_one(project_data)
        return project_data

    @classmethod
    async def get_project(cls, project_id: str) -> Optional[dict[str, Any]]:
        collection = cls.get_projects_collection()
        return await collection.find_one({"project_id": project_id})

    @classmethod
    async def get_all_projects(cls) -> list[dict[str, Any]]:
        collection = cls.get_projects_collection()
        cursor = collection.find({}).sort("created_at", -1)
        return await cursor.to_list(length=1000)

    @classmethod
    async def update_project(cls, project_id: str, updates: dict[str, Any]) -> bool:
        collection = cls.get_projects_collection()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await collection.update_one({"project_id": project_id}, {"$set": updates})
        return result.modified_count > 0

    @classmethod
    async def delete_project(cls, project_id: str) -> bool:
        collection = cls.get_projects_collection()
        result = await collection.delete_one({"project_id": project_id})
        return result.deleted_count > 0
