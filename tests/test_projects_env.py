import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.projects import handle_redeploy_all
from bot.utils.render_api import RenderAPI

@pytest.mark.asyncio
async def test_handle_redeploy_all_success():
    mock_client = MagicMock()
    mock_client.send_message = AsyncMock()

    mock_render = MagicMock()
    mock_render.list_services = AsyncMock(return_value=[
        {"service": {"id": "srv-1", "name": "app-one"}},
        {"service": {"id": "srv-2", "name": "app-two"}}
    ])
    mock_render.redeploy_service = AsyncMock(return_value=True)

    with patch("bot.database.mongo.db.get_user_render_key", AsyncMock(return_value="fake_key")), \
         patch("bot.handlers.projects.RenderAPI", return_value=mock_render):

        await handle_redeploy_all(mock_client, 12345, 999)

        assert mock_render.redeploy_service.call_count == 2
        mock_client.send_message.assert_called()

@pytest.mark.asyncio
async def test_redeploy_service_base_url_sync():
    render_api = RenderAPI("fake_api_key")

    mock_service_data = {
        "service": {
            "id": "srv-123",
            "name": "my-app",
            "serviceDetails": {"url": "https://my-app.onrender.com"}
        }
    }
    mock_env_vars = {
        "BASE_URL": "https://old-app.onrender.com",
        "DATABASE_URL": "mongodb://localhost:27017"
    }

    with patch.object(render_api, "get_service", new=AsyncMock(return_value=mock_service_data)), \
         patch.object(render_api, "get_env_vars", new=AsyncMock(return_value=mock_env_vars)), \
         patch.object(render_api, "update_env_vars", new=AsyncMock(return_value=True)) as mock_update_env, \
         patch.object(render_api, "_request", new=AsyncMock(return_value={"id": "dep-123"})) as mock_req:

        await render_api.redeploy_service("srv-123")

        # Must sync env vars prior to triggering redeployment
        mock_update_env.assert_called_once_with("srv-123", {
            "BASE_URL": "https://my-app.onrender.com",
            "DATABASE_URL": "mongodb://localhost:27017"
        })
        assert mock_req.call_args[0][1] == "/services/srv-123/deploys"
