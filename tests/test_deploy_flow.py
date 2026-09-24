import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.handlers.deploy import (
    DEPLOY_SESSIONS,
    wizard_text_input_handler,
    prompt_step_4_branch,
    confirm_deploy_callback
)
from bot.utils.render_api import RenderAPI, RenderAPIError

@pytest.mark.asyncio
async def test_deploy_flow_step_1_invalid_service_name():
    user_id = 12345
    DEPLOY_SESSIONS[user_id] = {"step": "AWAIT_SERVICE_NAME", "env_vars": {}, "type": "web_service"}

    client = MagicMock()
    client.send_message = AsyncMock()
    message = AsyncMock()
    message.from_user.id = user_id
    message.text = " "

    with patch("bot.database.mongo.db.get_user_github_token", new=AsyncMock(return_value="fake_token")):
        await wizard_text_input_handler(client, message)

    message.reply_text.assert_called_once()
    assert "Invalid Service Name" in message.reply_text.call_args[0][0]
    assert DEPLOY_SESSIONS[user_id]["step"] == "AWAIT_SERVICE_NAME"

@pytest.mark.asyncio
async def test_deploy_flow_step_1_valid_service_name():
    user_id = 12345
    DEPLOY_SESSIONS[user_id] = {"step": "AWAIT_SERVICE_NAME", "env_vars": {}, "type": "web_service"}

    client = MagicMock()
    client.send_message = AsyncMock()
    message = AsyncMock()
    message.from_user.id = user_id
    message.chat.id = 67890
    message.text = "My Cool Service! "

    with patch("bot.database.mongo.db.get_user_github_token", new=AsyncMock(return_value="fake_token")):
        await wizard_text_input_handler(client, message)

    assert DEPLOY_SESSIONS[user_id]["name"] == "my-cool-service"
    assert DEPLOY_SESSIONS[user_id]["step"] == "AWAIT_REPO"
    client.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_deploy_flow_step_2_repository_validation():
    user_id = 12345
    DEPLOY_SESSIONS[user_id] = {"step": "AWAIT_REPO", "name": "my-cool-service", "env_vars": {}, "type": "web_service"}

    client = MagicMock()
    client.send_message = AsyncMock()
    message = AsyncMock()
    message.from_user.id = user_id
    message.chat.id = 67890
    message.text = "https://github.com/testowner/testrepo"

    with patch("bot.database.mongo.db.get_user_github_token", new=AsyncMock(return_value="fake_token")):
        await wizard_text_input_handler(client, message)

    assert DEPLOY_SESSIONS[user_id]["repo"] == "https://github.com/testowner/testrepo"
    assert DEPLOY_SESSIONS[user_id]["owner"] == "testowner"
    assert DEPLOY_SESSIONS[user_id]["repo_name"] == "testrepo"
    assert DEPLOY_SESSIONS[user_id]["step"] == "AWAIT_RUNTIME"
    client.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_step_4_single_branch_auto_selection():
    user_id = 12345
    session = {
        "step": "AWAIT_BRANCH",
        "name": "my-service",
        "owner": "testowner",
        "repo_name": "single-branch-repo",
        "env": "docker",
        "is_docker": True
    }
    DEPLOY_SESSIONS[user_id] = session

    client = MagicMock()
    client.send_message = AsyncMock()

    with patch("bot.handlers.deploy.DockerInspector.fetch_repo_branches", new=AsyncMock(return_value=["main"])), \
         patch("bot.database.mongo.db.get_user_github_token", new=AsyncMock(return_value="fake_token")):

        await prompt_step_4_branch(client, 67890, user_id, session)

        assert DEPLOY_SESSIONS[user_id]["branch"] == "main"
        assert DEPLOY_SESSIONS[user_id]["step"] == "AWAIT_REGION"

@pytest.mark.asyncio
async def test_step_4_multiple_branches_menu():
    user_id = 12345
    session = {
        "step": "AWAIT_BRANCH",
        "name": "my-service",
        "owner": "testowner",
        "repo_name": "multi-branch-repo",
        "env": "docker",
        "is_docker": True
    }
    DEPLOY_SESSIONS[user_id] = session

    client = MagicMock()
    client.send_message = AsyncMock()
    message_to_edit = AsyncMock()

    with patch("bot.handlers.deploy.DockerInspector.fetch_repo_branches", new=AsyncMock(return_value=["main", "dev", "feature"])), \
         patch("bot.database.mongo.db.get_user_github_token", new=AsyncMock(return_value="fake_token")):

        await prompt_step_4_branch(client, 67890, user_id, session, message_to_edit=message_to_edit)

        assert DEPLOY_SESSIONS[user_id]["step"] == "AWAIT_BRANCH"
        message_to_edit.edit_text.assert_called()
        assert "3 Total" in message_to_edit.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_render_api_create_service_base_url_auto_formatting():
    render_api = RenderAPI("test_api_key")

    mock_resp = {
        "service": {
            "id": "srv-123456",
            "name": "test-service",
            "serviceDetails": {"url": "https://test-service.onrender.com"}
        }
    }

    config = {
        "name": "test-service",
        "repo": "https://github.com/owner/repo",
        "branch": "main",
        "type": "web_service",
        "env": "python",
        "is_docker": False,
        "region": "frankfurt",
        "plan": "free",
        "buildCommand": "pip install -r requirements.txt",
        "startCommand": "python app.py",
        "env_vars": {"FOO": "BAR", "BASE_URL": "http://old.com"}
    }

    with patch.object(render_api, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req, \
         patch.object(render_api, "get_owner_id", new=AsyncMock(return_value="usr-owner123")):

        res = await render_api.create_service(config)

        assert res == mock_resp
        payload = mock_req.call_args[1]["json_data"]
        env_vars = payload["serviceDetails"]["envVars"]

        # BASE_URL must be automatically updated to expected service url
        base_url_item = next(item for item in env_vars if item["key"] == "BASE_URL")
        assert base_url_item["value"] == "https://test-service.onrender.com"

@pytest.mark.asyncio
async def test_confirm_deploy_callback_402_handling():
    user_id = 9999
    DEPLOY_SESSIONS[user_id] = {
        "name": "my-free-app",
        "repo": "https://github.com/test/repo",
        "branch": "main",
        "plan": "free",
        "type": "web_service"
    }

    client = MagicMock()
    callback_query = AsyncMock()
    callback_query.from_user.id = user_id
    msg = AsyncMock()
    callback_query.message.edit_text = AsyncMock(return_value=msg)

    with patch("bot.database.mongo.db.get_user_render_key", new=AsyncMock(return_value="fake_render_key")), \
         patch("bot.utils.render_api.RenderAPI.create_service", new=AsyncMock(side_effect=RenderAPIError(402, "Payment information is required to complete this request."))) :

        await confirm_deploy_callback(client, callback_query)

        msg.edit_text.assert_called_once()
        err_text = msg.edit_text.call_args[0][0]
        assert "Deployment Failed (API Error 402)" in err_text
        assert "FREE" in err_text
        assert "https://dashboard.render.com/billing" in err_text
