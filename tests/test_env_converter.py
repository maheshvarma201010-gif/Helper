import pytest
from bot.utils.env_converter_util import convert_to_env, parse_env_input
from bot.utils.formatter import sanitize_service_name

def test_sanitize_service_name():
    assert sanitize_service_name("My Service Name") == "my-service-name"
    assert sanitize_service_name("my_repo_name!") == "my-repo-name"
    assert sanitize_service_name("---test---") == "test"
    assert sanitize_service_name("") == "app-service"
    assert sanitize_service_name(None, fallback="my-app") == "my-app"
    assert sanitize_service_name("Invalid@Characters#Here$$$") == "invalid-characters-here"

def test_convert_to_env_python_config():
    python_config = """
API_ID = 123456
API_HASH = "abc123hash"
BOT_TOKEN = '1234:xyz_token'
DEBUG = True
DATABASE_URL = "mongodb://localhost:27017/test"
PORT = 8080
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
    """
    res = convert_to_env(python_config)
    assert "API_ID=123456" in res
    assert "API_HASH=abc123hash" in res
    assert "BOT_TOKEN=1234:xyz_token" in res
    assert "DEBUG=True" in res
    assert "DATABASE_URL=mongodb://localhost:27017/test" in res

def test_convert_to_env_json():
    json_config = '{"PORT": 8080, "ENV": "production", "DB": {"host": "localhost"}}'
    res = convert_to_env(json_config)
    assert "PORT=8080" in res
    assert "ENV=production" in res
    assert 'DB={"host": "localhost"}' in res

def test_convert_to_env_ini_yaml_env():
    text_config = """
# Sample INI / YAML / ENV config
PORT: 8000
SECRET_KEY = supersecretvalue;
DATABASE_URI = postgresql://user:pass@localhost:5432/db
    """
    res = convert_to_env(text_config)
    assert "PORT=8000" in res
    assert "SECRET_KEY=supersecretvalue" in res
    assert "DATABASE_URI=postgresql://user:pass@localhost:5432/db" in res

def test_convert_to_env_codeflix_config():
    codeflix_config = """
import os
from os import getenv

TG_BOT_TOKEN = getenv("TG_BOT_TOKEN", "123456:ABC-DEF")
APP_ID = int(getenv("APP_ID", "12345"))
API_HASH = getenv("API_HASH", "abc123hash")
CHANNEL_ID = int(getenv("CHANNEL_ID", "-100123456"))
OWNER = getenv("OWNER", "codeflix")
OWNER_ID = int(getenv("OWNER_ID", "98765"))
PORT = int(os.environ.get("PORT", "8080"))
ANIME_BANNERS = ["https://telegra.ph/file/1.jpg", "https://telegra.ph/file/2.jpg"]
PICS = ANIME_BANNERS
"""
    res = convert_to_env(codeflix_config)
    assert "TG_BOT_TOKEN=123456:ABC-DEF" in res
    assert "APP_ID=12345" in res
    assert "API_HASH=abc123hash" in res
    assert "CHANNEL_ID=-100123456" in res
    assert "OWNER=codeflix" in res
    assert "OWNER_ID=98765" in res
    assert "PORT=8080" in res
    assert 'ANIME_BANNERS=["https://telegra.ph/file/1.jpg", "https://telegra.ph/file/2.jpg"]' in res
    assert 'PICS=["https://telegra.ph/file/1.jpg", "https://telegra.ph/file/2.jpg"]' in res
    assert "Call()" not in res

def test_parse_env_input_with_comments_and_quotes():
    raw_input = """
# Comment line
KEY1="value1" # Inline comment
export KEY2 = 'value2'
PORT=8080 // JS comment
"""
    parsed = parse_env_input(raw_input)
    assert parsed.get("KEY1") == "value1"
    assert parsed.get("KEY2") == "value2"
    assert parsed.get("PORT") == "8080"

def test_convert_to_env_empty():
    assert convert_to_env("") == ""
    assert convert_to_env("   \n\n  ") == ""
