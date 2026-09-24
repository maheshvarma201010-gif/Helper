import os
import shutil
import tempfile
import zipfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers.repo_upload import (
    REPO_UPLOAD_SESSIONS,
    cleanup_upload_session,
    create_github_branch_api,
    upload_extracted_files_to_branch,
    repo_upload_command,
    upload_zip_document_handler,
    repo_upload_text_handler,
    confirm_repo_upload_callback
)

@pytest.fixture
def mock_message():
    message = AsyncMock()
    message.from_user.id = 12345
    message.chat.id = 67890
    message.reply_text = AsyncMock()
    return message

@pytest.fixture
def mock_callback():
    cb = AsyncMock()
    cb.from_user.id = 12345
    cb.message.chat.id = 67890
    cb.message.edit_text = AsyncMock()
    return cb

@pytest.mark.asyncio
async def test_repo_upload_command_initialization(mock_message):
    await repo_upload_command(AsyncMock(), mock_message)
    assert 12345 in REPO_UPLOAD_SESSIONS
    assert REPO_UPLOAD_SESSIONS[12345]["step"] == "AWAIT_ZIP"
    mock_message.reply_text.assert_called_once()
    cleanup_upload_session(12345)

@pytest.mark.asyncio
async def test_upload_zip_document_handler_valid_zip(mock_message):
    user_id = 12345
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "test.zip")

    # Create dummy zip file
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("index.py", "print('hello')")

    REPO_UPLOAD_SESSIONS[user_id] = {"step": "AWAIT_ZIP"}

    doc = MagicMock()
    doc.file_name = "test.zip"
    mock_message.document = doc

    client = AsyncMock()
    async def fake_download(msg, file_name):
        shutil.copy2(zip_path, file_name)

    client.download_media = fake_download
    status_msg = AsyncMock()
    mock_message.reply_text = AsyncMock(return_value=status_msg)

    await upload_zip_document_handler(client, mock_message)

    assert REPO_UPLOAD_SESSIONS[user_id]["step"] == "AWAIT_REPO"
    status_msg.edit_text.assert_called_once()
    cleanup_upload_session(user_id)
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.mark.asyncio
async def test_repo_upload_text_handler_flow(mock_message):
    user_id = 12345
    REPO_UPLOAD_SESSIONS[user_id] = {
        "step": "AWAIT_REPO",
        "zip_name": "test.zip",
        "temp_dir": tempfile.mkdtemp(),
        "extract_dir": tempfile.mkdtemp()
    }

    # Step 1: Send Repo URL
    mock_message.text = "octocat/Hello-World"
    await repo_upload_text_handler(AsyncMock(), mock_message)
    assert REPO_UPLOAD_SESSIONS[user_id]["owner"] == "octocat"
    assert REPO_UPLOAD_SESSIONS[user_id]["repo"] == "Hello-World"
    assert REPO_UPLOAD_SESSIONS[user_id]["step"] == "AWAIT_BRANCH"

    # Step 2: Send Branch Name
    mock_message.text = "patch-1"
    with patch("bot.database.mongo.db.get_user_github_token", AsyncMock(return_value=None)):
        await repo_upload_text_handler(AsyncMock(), mock_message)
    assert REPO_UPLOAD_SESSIONS[user_id]["branch"] == "patch-1"
    assert REPO_UPLOAD_SESSIONS[user_id]["step"] == "AWAIT_USERNAME"

    # Step 3: Send Username
    mock_message.text = "octocat"
    await repo_upload_text_handler(AsyncMock(), mock_message)
    assert REPO_UPLOAD_SESSIONS[user_id]["username"] == "octocat"
    assert REPO_UPLOAD_SESSIONS[user_id]["step"] == "AWAIT_TOKEN"

    # Step 4: Send PAT Token
    mock_message.text = "ghp_1234567890abcdef"
    client = AsyncMock()
    await repo_upload_text_handler(client, mock_message)
    assert REPO_UPLOAD_SESSIONS[user_id]["step"] == "CONFIRMATION"
    client.send_message.assert_called_once()

    cleanup_upload_session(user_id)

@pytest.mark.asyncio
async def test_upload_extracted_files_to_branch_git():
    extract_dir = tempfile.mkdtemp()
    with open(os.path.join(extract_dir, "app.py"), "w") as f:
        f.write("print('Hello world')")

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.wait = AsyncMock(return_value=0)
        mock_exec.return_value = proc

        success, msg = await upload_extracted_files_to_branch(
            extract_dir, "octocat", "Hello-World", "feature", "octocat", "ghp_token"
        )
        assert success is True
        assert "Successfully created branch" in msg

    shutil.rmtree(extract_dir, ignore_errors=True)
