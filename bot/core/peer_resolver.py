import re
from typing import Union
from pyrogram import Client, errors
from pyrogram.errors import PeerIdInvalid, UsernameInvalid, ChannelInvalid, ChatInvalid
from bot.utils.exceptions import PeerError

class PeerResolver:
    @staticmethod
    async def resolve(client: Client, peer: Union[str, int]):
        try:
            # Handle numeric IDs
            if isinstance(peer, int):
                return await client.get_chat(peer)

            peer = str(peer).strip()

            # Handle invite links
            if "t.me/+" in peer or "t.me/joinchat/" in peer:
                try:
                    return await client.join_chat(peer)
                except errors.UserAlreadyParticipant:
                    # If already in, we still need to get the chat object
                    # We can try to extract the hash and use get_chat
                    pass

            # Handle message links/usernames
            if peer.startswith("https://t.me/"):
                peer = peer.replace("https://t.me/", "")
                if "/" in peer:
                    peer = peer.split("/")[0]

            if peer.startswith("@"):
                peer = peer[1:]

            # Handle private channel numeric IDs in links (t.me/c/12345/...)
            if peer.startswith("c/"):
                chat_id = int("-100" + peer.split("/")[1])
                return await client.get_chat(chat_id)

            return await client.get_chat(peer)

        except (PeerIdInvalid, UsernameInvalid, ChannelInvalid, ChatInvalid) as e:
            raise PeerError(f"Could not resolve peer '{peer}': {str(e)}")
        except Exception as e:
            raise PeerError(f"Unexpected error resolving peer '{peer}': {str(e)}")

    @staticmethod
    def extract_message_id(link: str) -> int:
        match = re.search(r"/(?:c/)?(?:[^/]+/)?(\d+)$", link)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def extract_chat_id(link: str) -> Union[str, int]:
        # Handle t.me/c/12345/678
        match = re.search(r"t\.me/c/(\d+)/", link)
        if match:
            return int("-100" + match.group(1))

        # Handle t.me/username/678
        match = re.search(r"t\.me/([^/]+)/", link)
        if match:
            return match.group(1)

        return None
