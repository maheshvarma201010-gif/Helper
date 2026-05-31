import re

def parse_message_link(link):
    """
    Parses a telegram message link and returns (chat_id, message_id)
    Example: https://t.me/c/123456789/10 or https://t.me/channel_name/10
    """
    pattern = r'https://t\.me/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        chat_id = match.group(1)
        if chat_id.isdigit():
            chat_id = int(f"-100{chat_id}")
        message_id = int(match.group(2))
        return chat_id, message_id
    return None, None
