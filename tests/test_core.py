import pytest
from bot.core.peer_resolver import PeerResolver

def test_extract_message_id():
    assert PeerResolver.extract_message_id("https://t.me/c/12345/678") == 678
    assert PeerResolver.extract_message_id("https://t.me/username/100") == 100
    assert PeerResolver.extract_message_id("https://t.me/username/abc") is None

def test_extract_chat_id():
    assert PeerResolver.extract_chat_id("https://t.me/c/12345/678") == -10012345
    assert PeerResolver.extract_chat_id("https://t.me/username/100") == "username"
