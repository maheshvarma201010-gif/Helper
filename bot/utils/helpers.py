import re

def parse_message_link(link):
    """
    Parses a telegram message link and returns (chat_id, message_id)
    Supports:
    - https://t.me/c/123456789/10
    - https://t.me/channel_username/10
    - tg://openmessage?chat_id=123456789&message_id=10
    """
    # Standard t.me link
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        chat_id = match.group(1)
        message_id = int(match.group(2))

        if chat_id.isdigit():
            # It's a private channel ID, add -100 prefix if not present
            chat_id_int = int(chat_id)
            if chat_id_int > 0:
                 chat_id_int = int(f"-100{chat_id_int}")
            return chat_id_int, message_id
        else:
            # It's a username
            return f"@{chat_id}", message_id

    # tg:// link
    pattern_tg = r'tg://openmessage\?chat_id=([\d-]+)&message_id=(\d+)'
    match_tg = re.search(pattern_tg, link)
    if match_tg:
        chat_id = int(match_tg.group(1))
        message_id = int(match_tg.group(2))
        return chat_id, message_id

    return None, None
