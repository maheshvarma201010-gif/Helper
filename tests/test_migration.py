import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.utils.migration import update_env_base_urls, execute_account_migration

def test_update_env_base_urls():
    old_env = {
        "PORT": "8080",
        "BASE_URL": "https://old-app.onrender.com",
        "WEBSITE_URL": "https://old-app.onrender.com/dash",
        "DATABASE_URL": "mongodb://localhost:27017/db"
    }

    updated = update_env_base_urls(old_env, "https://old-app.onrender.com", "https://new-app.onrender.com")

    assert updated["BASE_URL"] == "https://new-app.onrender.com"
    assert updated["WEBSITE_URL"] == "https://new-app.onrender.com"
    assert updated["PORT"] == "8080"
    assert updated["DATABASE_URL"] == "mongodb://localhost:27017/db"

@pytest.mark.asyncio
async def test_execute_account_migration():
    selected_services = [
        {
            "id": "srv_old1",
            "name": "Old App 1",
            "repo": "https://github.com/user/app1",
            "type": "web_service",
            "serviceDetails": {"url": "https://old1.onrender.com", "env": "docker"}
        }
    ]

    mock_old_render = MagicMock()
    mock_old_render.get_env_vars = AsyncMock(return_value={"BASE_URL": "https://old1.onrender.com"})
    mock_old_render.suspend_service = AsyncMock(return_value=True)

    mock_new_render = MagicMock()
    mock_new_render.create_service = AsyncMock(return_value={
        "service": {
            "id": "srv_new1",
            "name": "old-app-1",
            "serviceDetails": {"url": "https://new1.onrender.com"}
        }
    })
    mock_new_render.update_env_vars = AsyncMock(return_value=True)

    def render_api_factory(key):
        if key == "rnd_old":
            return mock_old_render
        return mock_new_render

    with patch("bot.utils.migration.RenderAPI", side_effect=render_api_factory), \
         patch("bot.database.mongo.db.save_deployment", AsyncMock()), \
         patch("bot.database.mongo.db.set_user_render_key", AsyncMock()):

        res = await execute_account_migration("rnd_old", "rnd_new", 12345, selected_services)

        assert res["success"] is True
        assert len(res["deployed"]) == 1
        assert res["deployed"][0]["url"] == "https://new1.onrender.com"
        mock_old_render.suspend_service.assert_called_once_with("srv_old1")
        mock_new_render.update_env_vars.assert_called_once()
