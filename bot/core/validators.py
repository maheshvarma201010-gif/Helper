from typing import List, Union
from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from bot.core.peer_resolver import PeerResolver

class Validators:
    @staticmethod
    async def verify_permissions(client: Client, chat_id: Union[str, int], is_bot: bool = False) -> bool:
        try:
            chat = await client.get_chat(chat_id)
            if is_bot:
                member = await chat.get_member("me")
                return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            return True # If userbot can get chat, it has access
        except Exception:
            return False

    @staticmethod
    def is_valid_message_link(link: str) -> bool:
        return bool(PeerResolver.extract_message_id(link))
