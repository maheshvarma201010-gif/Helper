import pytest
from bot.utils.env_converter_util import convert_to_env
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

def test_convert_to_env_empty():
    assert convert_to_env("") == ""
    assert convert_to_env("   \n\n  ") == ""
