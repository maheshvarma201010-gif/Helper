import logging
import base64
from typing import Optional, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    def connect(self):
        if not self.client:
            self.client = AsyncIOMotorClient(Config.MONGO_URI)
            self.db = self.client.get_default_database(default="render_deployer")
            logger.info("Connected to MongoDB")

    def _obfuscate(self, secret: str) -> str:
        if not secret:
            return ""
        key_bytes = Config.ENCRYPTION_SECRET.encode('utf-8')
        secret_bytes = secret.encode('utf-8')
        xor_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(secret_bytes)])
        return base64.b64encode(xor_bytes).decode('utf-8')

    def _deobfuscate(self, encoded: str) -> str:
        if not encoded:
            return ""
        try:
            xor_bytes = base64.b64decode(encoded.encode('utf-8'))
            key_bytes = Config.ENCRYPTION_SECRET.encode('utf-8')
            secret_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(xor_bytes)])
            return secret_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to deobfuscate secret: {e}")
            return ""

    async def get_user_render_key(self, user_id: int) -> Optional[str]:
        self.connect()
        doc = await self.db.users.find_one({"user_id": user_id})
        if doc and doc.get("render_api_key"):
            return self._deobfuscate(doc["render_api_key"])
        return None

    async def set_user_render_key(self, user_id: int, api_key: str):
        self.connect()
        enc_key = self._obfuscate(api_key)
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"render_api_key": enc_key, "updated_at": datetime.utcnow()}},
            upsert=True
        )

    async def get_user_github_token(self, user_id: int) -> Optional[str]:
        self.connect()
        doc = await self.db.users.find_one({"user_id": user_id})
        if doc and doc.get("github_token"):
            return self._deobfuscate(doc["github_token"])
        return None

    async def set_user_github_token(self, user_id: int, token: str):
        self.connect()
        enc_token = self._obfuscate(token)
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"github_token": enc_token, "updated_at": datetime.utcnow()}},
            upsert=True
        )

    async def remove_user_render_key(self, user_id: int):
        self.connect()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$unset": {"render_api_key": ""}, "$set": {"updated_at": datetime.utcnow()}}
        )

    async def save_deployment(self, user_id: int, service_id: str, service_name: str, repo_url: str, branch: str, service_type: str, is_docker: bool, status: str, service_url: Optional[str] = None):
        self.connect()
        record = {
            "user_id": user_id,
            "service_id": service_id,
            "service_name": service_name,
            "repo_url": repo_url,
            "branch": branch,
            "service_type": service_type,
            "is_docker": is_docker,
            "status": status,
            "service_url": service_url,
            "updated_at": datetime.utcnow()
        }
        await self.db.deployments.update_one(
            {"user_id": user_id, "service_id": service_id},
            {"$set": record, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )

    async def get_user_deployments(self, user_id: int) -> List[Dict[str, Any]]:
        self.connect()
        cursor = self.db.deployments.find({"user_id": user_id}).sort("updated_at", -1)
        return await cursor.to_list(length=100)

    async def get_all_deployments(self) -> List[Dict[str, Any]]:
        self.connect()
        cursor = self.db.deployments.find().sort("updated_at", -1)
        return await cursor.to_list(length=1000)

    async def save_uptime_status(self, service_id: str, is_up: bool, status_code: int, latency_ms: float):
        self.connect()
        now = datetime.utcnow()
        uptime_status = "UP" if is_up else "DOWN"
        await self.db.deployments.update_one(
            {"service_id": service_id},
            {"$set": {
                "uptime_status": uptime_status,
                "last_check_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "last_check_time": now
            }}
        )
        await self.db.uptime_logs.insert_one({
            "service_id": service_id,
            "status": uptime_status,
            "status_code": status_code,
            "latency_ms": round(latency_ms, 2),
            "timestamp": now
        })

    async def remove_deployment(self, user_id: int, service_id: str):
        self.connect()
        await self.db.deployments.delete_one({"user_id": user_id, "service_id": service_id})

    async def log_action(self, user_id: int, action: str, details: Dict[str, Any]):
        self.connect()
        log_entry = {
            "user_id": user_id,
            "action": action,
            "details": details,
            "timestamp": datetime.utcnow()
        }
        await self.db.audit_logs.insert_one(log_entry)

    async def is_authorized_user(self, user_id: int) -> bool:
        # Every user (admin or non-admin) is allowed to use the bot with their own keys.
        # Admin IDs can be used for administrative operations if needed, but non-admins are allowed.
        return True

    async def authorize_user(self, user_id: int):
        self.connect()
        await self.db.authorized_users.update_one(
            {"user_id": user_id},
            {"$set": {"authorized_at": datetime.utcnow()}},
            upsert=True
        )

db = Database()
