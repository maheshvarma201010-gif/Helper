import re
import logging

logger = logging.getLogger(__name__)

def parse_message_link(link):
    """
    Parses a telegram message link and returns (chat_id, message_id).
    Supports:
    - https://t.me/c/123456789/10 (Private)
    - https://t.me/channel_username/10 (Public)
    - tg://openmessage?chat_id=123456789&message_id=10
    """
    if not link:
        return None, None

    # Handle numeric chat_id strings directly
    if isinstance(link, str) and (link.startswith("-100") or link.isdigit()):
        try:
            val = int(link)
            if val > 0 and not str(val).startswith("-100"):
                val = int(f"-100{val}")
            return val, 0
        except: pass

    # Standard t.me link
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        chat_id_str = match.group(1)
        message_id = int(match.group(2))

        if chat_id_str.isdigit():
            chat_id = int(chat_id_str)
            if not str(chat_id).startswith("-100"):
                 chat_id = int(f"-100{chat_id}")
            return chat_id, message_id
        else:
            return f"@{chat_id_str}", message_id

    # tg:// link
    pattern_tg = r'tg://openmessage\?chat_id=([\d-]+)&message_id=(\d+)'
    match_tg = re.search(pattern_tg, link)
    if match_tg:
        chat_id = int(match_tg.group(1))
        message_id = int(match_tg.group(2))
        return chat_id, message_id

    return None, None

async def resolve_chat(client, chat_id):
    """
    Resiliently resolves a chat_id/username and ensures it's cached.
    """
    try:
        # If it's a numeric ID, try to get it directly
        return await client.get_chat(chat_id)
    except Exception as e:
        logger.warning(f"Failed to resolve {chat_id} directly: {e}")

        # If it's a username, try with the @ prefix if not present
        if isinstance(chat_id, str) and not chat_id.startswith("@") and not chat_id.startswith("-100"):
            try:
                return await client.get_chat(f"@{chat_id}")
            except: pass

        # Last resort: iterate dialogs to find it
        async for dialog in client.get_dialogs(limit=50):
            if str(dialog.chat.id) == str(chat_id) or dialog.chat.username == str(chat_id).replace("@", ""):
                return dialog.chat

    raise ValueError(f"Could not resolve chat {chat_id}")
