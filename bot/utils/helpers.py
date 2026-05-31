import re

def parse_message_link(link):
    """
    Parses a telegram message link and returns (chat_id, message_id).
    Supports:
    - https://t.me/c/123456789/10
    - https://t.me/channel_username/10
    - tg://openmessage?chat_id=123456789&message_id=10
    """
    if not link:
        return None, None

    # Handle numeric chat_id strings directly if passed instead of link
    if isinstance(link, str) and (link.startswith("-100") or link.isdigit()):
        try:
            return int(link), 0
        except:
            pass

    # Standard t.me link
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        chat_id_str = match.group(1)
        message_id = int(match.group(2))

        if chat_id_str.isdigit():
            chat_id = int(chat_id_str)
            # Standardize to -100 prefix for private channels
            if not str(chat_id).startswith("-100"):
                if chat_id > 0:
                     chat_id = int(f"-100{chat_id}")
                else:
                     # Already negative but maybe not -100 prefix?
                     # (Though usually it's either positive ID or -100 prefix)
                     pass
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
