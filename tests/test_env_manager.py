import pytest
from app.services.env_manager import EnvManager

def test_parse_env_content():
    content = """
    # Comment line
    PORT=8080
    SECRET_KEY="my_secret_val"
    DATABASE_URL='postgres://user:pass@localhost/db'
    EMPTY_VAL=
    """
    parsed = EnvManager.parse_env_content(content)
    assert parsed["PORT"] == "8080"
    assert parsed["SECRET_KEY"] == "my_secret_val"
    assert parsed["DATABASE_URL"] == "postgres://user:pass@localhost/db"
    assert parsed["EMPTY_VAL"] == ""

def test_mask_env_dict():
    env_vars = {
        "PUBLIC_NAME": "MyApp",
        "API_SECRET": "super_secret_key_12345",
        "KEY": "123"
    }
    masked = EnvManager.mask_env_dict(env_vars)
    assert masked["PUBLIC_NAME"] == "MyApp"
    assert "****" in masked["API_SECRET"]
    assert masked["KEY"] == "****"
