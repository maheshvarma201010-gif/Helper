import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.utils.limit_notifier import FreeTierLimitNotifier

@pytest.mark.asyncio
async def test_free_tier_limit_notifier():
    bot_client = AsyncMock()
    notifier = FreeTierLimitNotifier(bot_client=bot_client, check_interval=3600)

    mock_users = [{"user_id": 12345}]
    mock_services = [
        {"service": {"id": "srv_1", "suspended": "suspended", "serviceDetails": {"plan": "free"}}}
    ]

    mock_render = MagicMock()
    mock_render.list_services = AsyncMock(return_value=mock_services)

    with patch("bot.database.mongo.db.get_all_users", AsyncMock(return_value=mock_users)), \
         patch("bot.database.mongo.db.get_user_render_key", AsyncMock(return_value="rnd_mock")), \
         patch("bot.utils.limit_notifier.RenderAPI", return_value=mock_render):

        await notifier.check_and_notify_users()
        bot_client.send_message.assert_called_once()
        assert 12345 in bot_client.send_message.call_args[0]
        sent_msg = bot_client.send_message.call_args[0][1]
        assert "600 Hours" in sent_msg or "600 instance hours" in sent_msg
        assert "4 GB" in sent_msg
