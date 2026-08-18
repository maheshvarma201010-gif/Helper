import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.create_repo import create_github_repo, get_create_repo_choice_keyboard
from bot.database.mongo import Database

def test_get_create_repo_choice_keyboard():
    kb = get_create_repo_choice_keyboard()
    assert kb is not None
    assert len(kb.inline_keyboard) == 2
    buttons = kb.inline_keyboard[0]
    assert len(buttons) == 2
    assert "Import" in buttons[0].text
    assert "Create" in buttons[1].text

@pytest.mark.asyncio
async def test_create_github_repo_success():
    mock_resp = AsyncMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={
        "name": "test-repo",
        "full_name": "testuser/test-repo",
        "html_url": "https://github.com/testuser/test-repo",
        "default_branch": "main"
    })

    post_ctx = MagicMock()
    post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    post_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session_instance = MagicMock()
    mock_session_instance.post.return_value = post_ctx

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session_instance)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session_ctx):
        res = await create_github_repo("test-repo", "ghp_mock_token_123")
        assert res is not None
        assert res["name"] == "test-repo"
        assert res["full_name"] == "testuser/test-repo"

@pytest.mark.asyncio
async def test_create_github_repo_failure():
    mock_resp = AsyncMock()
    mock_resp.status = 422
    mock_resp.json = AsyncMock(return_value={"message": "Repository creation failed"})

    post_ctx = MagicMock()
    post_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    post_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session_instance = MagicMock()
    mock_session_instance.post.return_value = post_ctx

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session_instance)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session_ctx):
        res = await create_github_repo("invalid_name", "ghp_mock_token_123")
        assert res is None

@pytest.mark.asyncio
async def test_user_render_key_isolation():
    db = Database()
    db.connect = MagicMock()
    db.db = MagicMock()
    db.db.users.find_one = AsyncMock(return_value=None)

    key = await db.get_user_render_key(12345)
    assert key is None

@pytest.mark.asyncio
async def test_api_services_endpoint():
    from aiohttp.test_utils import TestClient, TestServer
    from bot.web.server import create_web_app
    from bot.database.mongo import db

    db.get_user_deployments = AsyncMock(return_value=[])

    app = create_web_app()
    client = TestClient(TestServer(app))
    await client.start_server()

    resp = await client.get("/api/services?user_id=invalid")
    assert resp.status == 400

    resp_valid = await client.get("/api/services?user_id=12345")
    assert resp_valid.status == 200
    data = await resp_valid.json()
    assert data["status"] == "success"
    assert "summary" in data
    assert "services" in data

    await client.close()
