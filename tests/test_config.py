import os
import pytest
from app.config import Config

def test_config_parsing(monkeypatch):
    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "test_hash")
    monkeypatch.setenv("BOT_TOKEN", "test_token")
    monkeypatch.setenv("ADMIN_IDS", "111, 222, 333")
    monkeypatch.setenv("OWNER_ID", "999")
    monkeypatch.setenv("BASE_URL", "https://example.com")
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")

    # Reload values from environment
    Config.API_ID = int(os.getenv("API_ID"))
    Config.API_HASH = os.getenv("API_HASH")
    Config.BOT_TOKEN = os.getenv("BOT_TOKEN")
    Config.ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS").split(",")]
    Config.OWNER_ID = int(os.getenv("OWNER_ID"))
    Config.BASE_URL = os.getenv("BASE_URL")
    Config.MONGODB_URL = os.getenv("MONGODB_URL")

    assert Config.API_ID == 12345
    assert Config.OWNER_ID == 999
    assert Config.ADMIN_IDS == [111, 222, 333]
    assert Config.is_authorized(999) is True
    assert Config.is_authorized(111) is True
    assert Config.is_authorized(444) is False
    assert Config.validate() == []
