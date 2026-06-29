import asyncio
from typing import Dict
from pyrogram import Client
from bot.config import Config
from bot.database.sessions import get_session, get_all_sessions
from bot.core.logger import logger

class ClientManager:
    def __init__(self):
        self.user_clients: Dict[int, Client] = {}
        self.bot_client: Client = None

    async def init_bot(self):
        self.bot_client = Client(
            "bot_session",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/plugins")
        )
        await self.bot_client.start()
        logger.info("Bot client started.")

    async def load_user_sessions(self):
        sessions = await get_all_sessions()
        for session in sessions:
            user_id = session["user_id"]
            session_string = session["session_string"]
            try:
                client = Client(
                    name=f"user_{user_id}",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await client.start()
                self.user_clients[user_id] = client
                logger.info(f"Started user client for {user_id}")
            except Exception as e:
                logger.error(f"Failed to start user client for {user_id}: {e}")

    async def get_user_client(self, user_id: int) -> Client:
        if user_id in self.user_clients:
            return self.user_clients[user_id]

        session_string = await get_session(user_id)
        if session_string:
            try:
                client = Client(
                    name=f"user_{user_id}",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await client.start()
                self.user_clients[user_id] = client
                return client
            except Exception as e:
                logger.error(f"Failed to start user client for {user_id}: {e}")
        return None

    async def stop_user_client(self, user_id: int):
        if user_id in self.user_clients:
            try:
                await self.user_clients[user_id].stop()
            except:
                pass
            del self.user_clients[user_id]

client_manager = ClientManager()
