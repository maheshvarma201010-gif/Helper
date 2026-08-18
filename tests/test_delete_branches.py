import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.utils.docker_inspector import DockerInspector
from bot.handlers.delete_branches import build_delete_branches_keyboard, DELETE_BRANCHES_SESSIONS

@pytest.mark.asyncio
async def test_delete_repo_branch_success():
    mock_resp = AsyncMock()
    mock_resp.status = 204

    delete_ctx = MagicMock()
    delete_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    delete_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.delete.return_value = delete_ctx

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session_ctx):
        res = await DockerInspector.delete_repo_branch("owner", "repo", "feat-branch", "ghp_mock_token_123")
        assert res is True

@pytest.mark.asyncio
async def test_delete_repo_branch_failure():
    mock_resp = AsyncMock()
    mock_resp.status = 404

    delete_ctx = MagicMock()
    delete_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    delete_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.delete.return_value = delete_ctx

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session_ctx):
        res = await DockerInspector.delete_repo_branch("owner", "repo", "nonexistent", "ghp_mock_token_123")
        assert res is False

def test_build_delete_branches_keyboard():
    user_id = 999111
    DELETE_BRANCHES_SESSIONS[user_id] = {
        "branches": ["main", "dev", "feature-1"],
        "selected": {"dev"},
        "page": 0
    }

    kb = build_delete_branches_keyboard(user_id)
    assert kb is not None
    # Verify checkboxes in keyboard
    flat_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("☑️ dev" in t for t in flat_texts)
    assert any("🔲 main" in t for t in flat_texts)
    assert any("Delete (1)" in t for t in flat_texts)
