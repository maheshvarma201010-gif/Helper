import re

def parse_message_link(link):
    """
    Parses a telegram message link and returns (chat_id, message_id).
    Supports:
    - https://t.me/c/123456789/10 (Private channel)
    - https://t.me/channel_username/10 (Public channel)
    - tg://openmessage?chat_id=123456789&message_id=10 (Direct deep link)
    """
    if not link:
        return None, None

    # Standard t.me link
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        chat_id_str = match.group(1)
        message_id = int(match.group(2))

        if chat_id_str.isdigit():
            # Private channel ID. Ensure -100 prefix for Pyrogram
            chat_id = int(chat_id_str)
            if not str(chat_id).startswith("-100"):
                 chat_id = int(f"-100{chat_id}")
            return chat_id, message_id
        else:
            # Public channel username. Prefix with @ for Pyrogram
            return f"@{chat_id_str}", message_id

    # tg:// deep link
    pattern_tg = r'tg://openmessage\?chat_id=([\d-]+)&message_id=(\d+)'
    match_tg = re.search(pattern_tg, link)
    if match_tg:
        chat_id = int(match_tg.group(1))
        message_id = int(match_tg.group(2))
        return chat_id, message_id

    return None, None
