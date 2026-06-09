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
        self.domain_jobs = self.db["domain_jobs"]
        self.forward_jobs = self.db["forward_jobs"]
        self.button_configs = self.db["button_configs"]

        # New collections for Userbot and Search
        self.settings = self.db["settings"]
        self.channels = self.db["channels"]
        self.indexes = self.db["indexes"]
        self.search_cache = self.db["search_cache"]
        self.batches = self.db["batches"]
        self.fonts = self.db["fonts"]
        self.tedit_settings = self.db["tedit_settings"]
        self.tedit_jobs = self.db["tedit_jobs"]
        self.tedit_monitoring = self.db["tedit_monitoring"]
        self.auto_approve = self.db["auto_approve"]

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

    # Sessions
    async def set_session(self, user_id, string_session):
        await self.sessions.update_one({"user_id": user_id}, {"$set": {"session": string_session}}, upsert=True)

    async def get_session(self, user_id):
        data = await self.sessions.find_one({"user_id": user_id})
        return data["session"] if data else None

    # Button Configurations
    async def set_button_config(self, user_id, config):
        await self.button_configs.update_one({"user_id": user_id}, {"$set": config}, upsert=True)

    async def get_button_config(self, user_id):
        return await self.button_configs.find_one({"user_id": user_id})

    async def delete_button_config(self, user_id):
        await self.button_configs.delete_one({"user_id": user_id})

    # Forward Jobs
    async def add_forward_job(self, job_data):
        await self.forward_jobs.insert_one(job_data)

    async def update_forward_job(self, job_id, update_data):
        await self.forward_jobs.update_one({"job_id": job_id}, {"$set": update_data})

    async def get_forward_job(self, job_id):
        return await self.forward_jobs.find_one({"job_id": job_id})

    async def get_active_forward_job(self, user_id):
        return await self.forward_jobs.find_one({"user_id": user_id, "status": {"$in": ["running", "paused", "queued"]}})

    async def get_all_active_forward_jobs(self):
        return await self.forward_jobs.find({"status": {"$in": ["running", "paused", "queued"]}}).to_list(length=None)

    # Settings and Channels
    async def set_source_channel(self, channel_id):
        await self.settings.update_one({"key": "source_channel"}, {"$set": {"value": channel_id}}, upsert=True)

    async def get_source_channel(self):
        setting = await self.settings.find_one({"key": "source_channel"})
        return setting["value"] if setting else None

    async def set_batch_bot(self, username):
        await self.settings.update_one({"key": "batch_bot"}, {"$set": {"value": username}}, upsert=True)

    async def get_batch_bot(self):
        setting = await self.settings.find_one({"key": "batch_bot"})
        return setting["value"] if setting else None

    # Global task lock for Domain Replacement
    async def is_domain_job_running(self):
        job = await self.settings.find_one({"key": "domain_job_active"})
        return job["value"] if job else False

    async def set_domain_job_status(self, status):
        await self.settings.update_one({"key": "domain_job_active"}, {"$set": {"value": status}}, upsert=True)

    # Domain Job Data
    async def update_domain_data(self, user_id, data):
        await self.domain_jobs.update_one({"user_id": user_id}, {"$set": data}, upsert=True)

    async def get_domain_data(self, user_id):
        return await self.domain_jobs.find_one({"user_id": user_id})

    async def clear_domain_data(self, user_id):
        await self.domain_jobs.delete_one({"user_id": user_id})

    # Indexing
    async def add_index(self, data):
        await self.indexes.update_one(
            {"chat_id": data["chat_id"], "message_id": data["message_id"]},
            {"$set": data},
            upsert=True
        )

    async def get_latest_indexed_id(self, chat_id):
        latest = await self.indexes.find_one({"chat_id": chat_id}, sort=[("message_id", -1)])
        return latest["message_id"] if latest else 0

    async def get_recent_posts(self, hours=24):
        import datetime
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)
        return await self.indexes.find({"timestamp": {"$gte": since}}).sort("timestamp", -1).to_list(length=100)

    async def get_all_indexed(self, limit=100, skip=0):
        return await self.indexes.find().sort("message_id", -1).skip(skip).to_list(length=limit)

    async def search_index(self, query_filter):
        return await self.indexes.find(query_filter).to_list(length=1000)

    # Sequence and Replace methods
    async def add_sequence_file(self, user_id, file_data):
        await self.sequences.update_one({"user_id": user_id}, {"$push": {"files": file_data}}, upsert=True)

    async def get_sequence_files(self, user_id):
        job = await self.sequences.find_one({"user_id": user_id})
        return job.get("files", []) if job else []

    async def clear_sequence_files(self, user_id):
        await self.sequences.delete_one({"user_id": user_id})

    async def update_replace_data(self, user_id, data):
        await self.replace_jobs.update_one({"user_id": user_id}, {"$set": data}, upsert=True)

    async def get_replace_data(self, user_id):
        return await self.replace_jobs.find_one({"user_id": user_id})

    async def clear_replace_data(self, user_id):
        await self.replace_jobs.delete_one({"user_id": user_id})

    # Font Settings
    async def set_channel_font(self, channel_id, font_style):
        await self.fonts.update_one(
            {"channel_id": channel_id},
            {"$set": {"font_style": font_style}},
            upsert=True
        )

    async def get_channel_font(self, channel_id):
        data = await self.fonts.find_one({"channel_id": channel_id})
        return data["font_style"] if data else None

    async def delete_channel_font(self, channel_id):
        await self.fonts.delete_one({"channel_id": channel_id})

    # TEdit Settings
    async def set_tedit_settings(self, user_id, settings):
        await self.tedit_settings.update_one({"user_id": user_id}, {"$set": settings}, upsert=True)

    async def get_tedit_settings(self, user_id):
        return await self.tedit_settings.find_one({"user_id": user_id})

    # TEdit Jobs
    async def add_tedit_job(self, job_data):
        await self.tedit_jobs.insert_one(job_data)

    async def update_tedit_job(self, job_id, update_data):
        await self.tedit_jobs.update_one({"job_id": job_id}, {"$set": update_data})

    async def get_tedit_job(self, job_id):
        return await self.tedit_jobs.find_one({"job_id": job_id})

    async def get_active_tedit_job(self, user_id):
        return await self.tedit_jobs.find_one({"user_id": user_id, "status": {"$in": ["running", "paused", "queued"]}})

    async def get_all_active_tedit_jobs(self):
        return await self.tedit_jobs.find({"status": {"$in": ["running", "paused", "queued"]}}).to_list(length=None)

    # TEdit Monitoring
    async def set_tedit_monitoring(self, user_id, channel_id, status=True, settings=None):
        if status:
            update_data = {"active": True}
            if settings:
                update_data["settings"] = settings
            await self.tedit_monitoring.update_one(
                {"user_id": user_id, "channel_id": channel_id},
                {"$set": update_data},
                upsert=True
            )
        else:
            await self.tedit_monitoring.delete_one({"user_id": user_id, "channel_id": channel_id})

    async def get_tedit_monitoring(self, channel_id):
        return await self.tedit_monitoring.find({"channel_id": channel_id, "active": True}).to_list(length=None)

    async def get_user_monitoring(self, user_id):
        return await self.tedit_monitoring.find({"user_id": user_id, "active": True}).to_list(length=None)

    # Auto Approve
    async def set_auto_approve(self, chat_id, status: bool):
        await self.auto_approve.update_one(
            {"chat_id": chat_id},
            {"$set": {"active": status}},
            upsert=True
        )

    async def get_auto_approve(self, chat_id):
        data = await self.auto_approve.find_one({"chat_id": chat_id})
        return data["active"] if data else False

db = Database()
