import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from bot.utils.uptime_monitor import UptimeMonitor
from bot.database.mongo import Database

@pytest.mark.asyncio
async def test_uptime_check_service_url():
    monitor = UptimeMonitor()
    assert monitor.check_interval == 10

    mock_resp = AsyncMock()
    mock_resp.status = 200

    get_ctx = MagicMock()
    get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    get_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get.return_value = get_ctx

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session_ctx):
        is_up, status_code, latency = await monitor._check_service_url("https://example.com")
        assert is_up is True
        assert status_code == 200
        assert latency >= 0

@pytest.mark.asyncio
async def test_uptime_check_all_services():
    monitor = UptimeMonitor()

    mock_deployments = [
        {
            "service_id": "srv_123",
            "service_name": "My App",
            "user_id": 999,
            "service_url": "https://myapp.onrender.com"
        }
    ]

    with patch("bot.database.mongo.db.get_all_deployments", AsyncMock(return_value=mock_deployments)), \
         patch("bot.database.mongo.db.save_uptime_status", AsyncMock()) as mock_save, \
         patch.object(monitor, "_check_service_url", AsyncMock(return_value=(True, 200, 45.5))):

        await monitor.check_all_services()
        mock_save.assert_called_once_with("srv_123", True, 200, 45.5)

@pytest.mark.asyncio
async def test_mongo_save_uptime_status():
    db = Database()
    db.connect = MagicMock()
    db.db = MagicMock()
    db.db.deployments.update_one = AsyncMock()
    db.db.uptime_logs.insert_one = AsyncMock()

    await db.save_uptime_status("srv_test", True, 200, 120.0)
    db.db.deployments.update_one.assert_called_once()
    db.db.uptime_logs.insert_one.assert_called_once()
