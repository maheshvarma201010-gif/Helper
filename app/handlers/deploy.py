import os
import tempfile
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import Config
from app.database import Database
from app.services.docker_manager import DockerManager
from app.services.deployment_manager import DeploymentManager

logger = logging.getLogger(__name__)

# State tracking for user upload flow
# { user_id: {"action": "deploy" | "replace", "project_id": str | None} }
USER_STATE = {}

@Client.on_message(filters.command("deploy") & filters.private)
async def deploy_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    if not DockerManager.is_docker_available():
        await message.reply_text("❌ Docker Engine is not available in the current hosting environment.")
        return

    USER_STATE[user_id] = {"action": "deploy", "project_id": None}
    await message.reply_text("📦 Send your repository ZIP file.\n\nThe ZIP must contain a Dockerfile.")

@Client.on_message(filters.document & filters.private)
async def document_upload_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        return

    state = USER_STATE.get(user_id)
    if not state or state.get("action") not in ("deploy", "replace"):
        return

    document = message.document
    if not document or not document.file_name.lower().endswith(".zip"):
        await message.reply_text("⚠️ Please upload a valid ZIP file ending with `.zip`.")
        return

    action = state.get("action")
    target_project_id = state.get("project_id")
    USER_STATE.pop(user_id, None)

    status_msg = await message.reply_text("📥 Downloading ZIP file...")

    temp_dir = tempfile.mkdtemp()
    temp_zip_path = os.path.join(temp_dir, document.file_name)

    try:
        await message.download(file_name=temp_zip_path)

        async def update_status(text: str):
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

        if action == "deploy":
            success, result_text, project_doc = await DeploymentManager.deploy_new_project(
                zip_file_path=temp_zip_path,
                zip_filename=document.file_name,
                admin_id=user_id,
                status_callback=update_status
            )
            if success and project_doc:
                await status_msg.edit_text(
                    f"✅ Deployment successful!\n\n"
                    f"📦 Name: {project_doc['project_name']}\n"
                    f"🆔 ID: {project_doc['project_id']}\n"
                    f"🐳 Container: {project_doc['container_name']}\n"
                    f"📌 Status: {project_doc['status']}"
                )
            else:
                await status_msg.edit_text(f"❌ Deployment failed:\n\n{result_text}")

        elif action == "replace" and target_project_id:
            success, result_text = await DeploymentManager.replace_project_zip(
                project_id=target_project_id,
                zip_file_path=temp_zip_path,
                zip_filename=document.file_name,
                status_callback=update_status
            )
            await status_msg.edit_text(result_text)

    except Exception as e:
        logger.exception("Error processing uploaded document")
        await status_msg.edit_text(f"❌ An error occurred during process: {str(e)}")
    finally:
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
