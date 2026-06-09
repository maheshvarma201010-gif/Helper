import re
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.stylizer import get_available_fonts

logger = logging.getLogger(__name__)

def parse_message_link(link):
    """
    Parses a telegram message link and returns (chat_id, first_id, last_id).
    Supports:
    - https://t.me/c/123456789/10 (Single)
    - https://t.me/c/123456789/10-20 (Range)
    - https://t.me/channel/10 (Public)
    - https://t.me/channel/10-20 (Public Range)
    """
    if not link:
        return None, None, None

    # Standard t.me link pattern including ranges
    # Matches: https://t.me/c/123/10 or https://t.me/c/123/10-20 or https://t.me/username/10
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)(?:-(\d+))?'
    match = re.search(pattern, link)

    if match:
        chat_id_str = match.group(1)
        first_id = int(match.group(2))
        last_id = int(match.group(3)) if match.group(3) else first_id

        # chat_id_str could be '123' (private) or 'username' (public)
        if chat_id_str.lstrip("-").isdigit():
            chat_id = int(chat_id_str)
            if not str(chat_id).startswith("-100"):
                 chat_id = int(f"-100{chat_id}")
            return chat_id, first_id, last_id
        else:
            chat_id = f"@{chat_id_str}"
            return chat_id, first_id, last_id

    # Handle numeric chat_id strings directly
    if isinstance(link, str) and (link.startswith("-100") or link.isdigit()):
        try:
            val = int(link)
            if val > 0 and not str(val).startswith("-100"):
                val = int(f"-100{val}")
            return val, 0, 0
        except: pass

    return None, None, None

async def resolve_chat(client, chat_id):
    """
    Resiliently resolves a chat_id/username/link and ensures it's cached.
    """
    if not isinstance(chat_id, str):
        try:
            return await client.get_chat(chat_id)
        except:
            raise ValueError(f"Could not resolve chat {chat_id}.")

    # Handle invite links / join links
    if "t.me/+" in chat_id or "t.me/joinchat/" in chat_id:
        try:
            return await client.join_chat(chat_id)
        except Exception as e:
             logger.warning(f"Failed to join chat via link: {e}")
             # If already joined, get_chat might still work
             pass

    # Clean username/id
    clean_id = chat_id.split("/")[-1] if "/" in chat_id else chat_id

    try:
        # Try direct
        return await client.get_chat(clean_id)
    except Exception as e:
        logger.warning(f"Failed to resolve {clean_id} directly: {e}")

        # Try with @ prefix
        if not clean_id.startswith("@") and not clean_id.lstrip("-").isdigit():
            try:
                return await client.get_chat(f"@{clean_id}")
            except: pass

    raise ValueError(f"Could not resolve chat {chat_id}. Ensure the bot is an admin in the channel or the link is valid.")

def get_font_markup(action, channel_id=None):
    """
    Generates a markup for font selection.
    """
    buttons = []
    fonts = get_available_fonts()
    # Chunk fonts into 2 per row
    for i in range(0, len(fonts), 2):
        row = []
        for font in fonts[i:i+2]:
            callback_data = f"font:{action}:{font}"
            if channel_id:
                callback_data += f":{channel_id}"
            row.append(InlineKeyboardButton(font.replace("_", " ").title(), callback_data=callback_data))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)
