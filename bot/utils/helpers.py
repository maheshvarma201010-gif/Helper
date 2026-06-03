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
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)(?:-(\d+))?'
    match = re.search(pattern, link)

    if match:
        chat_id_str = match.group(1)
        first_id = int(match.group(2))
        last_id = int(match.group(3)) if match.group(3) else first_id

        if chat_id_str.isdigit():
            chat_id = int(chat_id_str)
            if not str(chat_id).startswith("-100"):
                 chat_id = int(f"-100{chat_id}")
            return chat_id, first_id, last_id
        else:
            return f"@{chat_id_str}", first_id, last_id

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

    raise ValueError(f"Could not resolve chat {chat_id}. Ensure the bot is an admin in the channel.")

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
