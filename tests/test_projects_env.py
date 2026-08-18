import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.projects import handle_redeploy_all

@pytest.mark.asyncio
async def test_handle_redeploy_all_success():
    mock_render = MagicMock()
    mock_render.list_services = AsyncMock(return_value=[
        {"service": {"id": "srv_1", "name": "App 1"}},
        {"service": {"id": "srv_2", "name": "App 2"}}
    ])
    mock_render.redeploy_service = AsyncMock(return_value=True)

    mock_client = AsyncMock()
    mock_msg = AsyncMock()
    mock_client.send_message.return_value = mock_msg

    with patch("bot.database.mongo.db.get_user_render_key", AsyncMock(return_value="rnd_test")), \
         patch("bot.handlers.projects.RenderAPI", return_value=mock_render):

        await handle_redeploy_all(mock_client, 12345, 999)

        assert mock_render.redeploy_service.call_count == 2
        mock_msg.edit_text.assert_called_once()
