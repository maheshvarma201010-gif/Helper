import re
from typing import Union
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, UsernameInvalid, ChannelInvalid, ChatInvalid
from bot.utils.exceptions import PeerError

class PeerResolver:
    @staticmethod
    async def resolve(client: Client, peer: Union[str, int]):
        try:
            # Handle numeric IDs
            if isinstance(peer, int):
                return await client.get_chat(peer)

            # Handle usernames and links
            if isinstance(peer, str):
                peer = peer.strip()
                if peer.startswith("https://t.me/"):
                    peer = peer.replace("https://t.me/", "")
                    if "/" in peer:
                        # Probably a private link or message link, handle appropriately
                        # For simplicity, we try to get the chat from the username part
                        peer = peer.split("/")[0]

                if peer.startswith("@"):
                    peer = peer[1:]

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
