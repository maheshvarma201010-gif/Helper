import os
import io
import tempfile
import logging
from typing import Tuple, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import Config
from app.database import Database
from app.services.docker_manager import DockerManager
from app.services.deployment_manager import DeploymentManager
from app.services.env_manager import EnvManager
from app.handlers.deploy import USER_STATE

logger = logging.getLogger(__name__)

# Helper to select a project for a command if no argument supplied
async def select_project_keyboard(command_prefix: str) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    projects = await Database.get_all_projects()
    if not projects:
        return "📦 No projects found.", None

    buttons = []
    for proj in projects:
        p_id = proj["project_id"]
        p_name = proj["project_name"]
        buttons.append([InlineKeyboardButton(f"📦 {p_name} ({p_id})", callback_data=f"{command_prefix}:{p_id}")])

    return f"Select project for command:", InlineKeyboardMarkup(buttons)

# --- /PAUSE ---
@Client.on_message(filters.command("pause") & filters.private)
async def pause_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_pause")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("⏸ Select a project to pause:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_pause:(.+)"))
async def callback_pause(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_pause:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    success, msg = await DockerManager.pause_container(project["container_name"])
    if success:
        await Database.update_project(project_id, {"status": "PAUSED"})
        await callback_query.message.edit_text(f"⏸ Project '{project['project_name']}' paused successfully.")
    else:
        await callback_query.message.edit_text(f"❌ Failed to pause project:\n{msg}")
    await callback_query.answer()

# --- /STOP ---
@Client.on_message(filters.command("stop") & filters.private)
async def stop_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_stop")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("🛑 Select a project to stop:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_stop:(.+)"))
async def callback_stop(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_stop:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    success, msg = await DockerManager.stop_container(project["container_name"])
    if success:
        await Database.update_project(project_id, {"status": "STOPPED"})
        await callback_query.message.edit_text(f"🛑 Project '{project['project_name']}' stopped successfully.")
    else:
        await callback_query.message.edit_text(f"❌ Failed to stop project:\n{msg}")
    await callback_query.answer()

# --- /STARTPROJECT ---
@Client.on_message(filters.command("startproject") & filters.private)
async def startproject_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_start")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("▶️ Select a project to start:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_start:(.+)"))
async def callback_start(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_start:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    success, msg = await DockerManager.start_container(project["container_name"])
    if success:
        await Database.update_project(project_id, {"status": "RUNNING", "last_error": None})
        await callback_query.message.edit_text(f"▶️ Project '{project['project_name']}' started successfully.")
    else:
        await Database.update_project(project_id, {"status": "FAILED", "last_error": msg})
        await callback_query.message.edit_text(f"⚠️ Container started but exited.\n\n{msg}")
    await callback_query.answer()

# --- /RESTART ---
@Client.on_message(filters.command("restart") & filters.private)
async def restart_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_restart")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("🔄 Select a project to restart:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_restart:(.+)"))
async def callback_restart(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_restart:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    success, msg = await DockerManager.restart_container(project["container_name"])
    if success:
        await Database.update_project(project_id, {"status": "RUNNING", "last_error": None})
        await callback_query.message.edit_text(f"🔄 Project '{project['project_name']}' restarted successfully.")
    else:
        await Database.update_project(project_id, {"status": "FAILED", "last_error": msg})
        await callback_query.message.edit_text(f"❌ Restart failed:\n{msg}")
    await callback_query.answer()

# --- /REDEPLOY ---
@Client.on_message(filters.command("redeploy") & filters.private)
async def redeploy_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_redeploy")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("🚀 Select a project to redeploy:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_redeploy:(.+)"))
async def callback_redeploy(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_redeploy:")[1]

    async def update_msg(text: str):
        try:
            await callback_query.message.edit_text(text)
        except Exception:
            pass

    success, msg = await DeploymentManager.redeploy_project(project_id, status_callback=update_msg)
    await callback_query.message.edit_text(msg)
    await callback_query.answer()

# --- /LOGS ---
@Client.on_message(filters.command("logs") & filters.private)
async def logs_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_logs")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("📜 Select a project to view logs:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_logs:(.+)"))
async def callback_logs(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_logs:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    success, logs_text = await DockerManager.get_container_logs(project["container_name"], tail=200)
    if not success:
        await callback_query.message.edit_text(f"❌ Error getting logs:\n{logs_text}")
        await callback_query.answer()
        return

    if len(logs_text) <= 3000:
        await callback_query.message.edit_text(f"📜 LOGS FOR '{project['project_name']}' ({project_id}):\n\n```\n{logs_text}\n```")
    else:
        # Send as document file
        file_bytes = io.BytesIO(logs_text.encode("utf-8"))
        file_bytes.name = f"{project['project_name']}-logs.txt"
        await client.send_document(
            chat_id=callback_query.message.chat.id,
            document=file_bytes,
            caption=f"📜 Logs for '{project['project_name']}' ({project_id})"
        )
        await callback_query.message.edit_text("📜 Logs sent as text file above.")

    await callback_query.answer()

# --- /ENV ---
@Client.on_message(filters.command("env") & filters.private)
async def env_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_env")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("⚙️ Select a project to upload/update .env:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_env:(.+)"))
async def callback_env(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_env:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    USER_STATE[user_id] = {"action": "upload_env", "project_id": project_id}
    await callback_query.message.edit_text(
        f"⚙️ Upload `.env` file or send text content for:\n\n"
        f"📦 Project: {project['project_name']}\n"
        f"🆔 ID: {project_id}\n\n"
        f"Reply with a `.env` document file or formatted text (`KEY=value`)."
    )
    await callback_query.answer()

@Client.on_message((filters.document | filters.text) & filters.private, group=1)
async def env_upload_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        return

    state = USER_STATE.get(user_id)
    if not state or state.get("action") != "upload_env":
        return

    project_id = state.get("project_id")
    USER_STATE.pop(user_id, None)

    project = await Database.get_project(project_id)
    if not project:
        await message.reply_text("❌ Target project not found.")
        return

    env_content = ""
    if message.document:
        # Download document into memory or temp path
        temp_dir = tempfile.mkdtemp()
        env_file_path = os.path.join(temp_dir, message.document.file_name)
        try:
            await message.download(file_name=env_file_path)
            with open(env_file_path, "r", encoding="utf-8", errors="ignore") as f:
                env_content = f.read()
        except Exception as e:
            await message.reply_text(f"❌ Failed to read uploaded file: {e}")
            return
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    elif message.text:
        env_content = message.text

    new_env_vars = EnvManager.parse_env_content(env_content)
    if not new_env_vars:
        await message.reply_text("⚠️ No valid environment variables parsed from input.")
        return

    status_msg = await message.reply_text("⚙️ Saving environment configuration and restarting project...")

    await Database.update_project(project_id, {"env_vars": new_env_vars})

    # Recreate container with new env vars
    image_name = project["image_name"]
    container_name = project["container_name"]

    start_success, start_msg, _ = await DockerManager.create_and_start_container(
        image_name=image_name,
        container_name=container_name,
        env_vars=new_env_vars
    )

    if start_success:
        await Database.update_project(project_id, {"status": "RUNNING", "last_error": None})
        await status_msg.edit_text("✅ Environment updated and project restarted successfully.")
    else:
        await Database.update_project(project_id, {"status": "FAILED", "last_error": start_msg})
        await status_msg.edit_text(f"❌ Environment saved, but container restart failed:\n{start_msg}")

# --- /REMOVE ---
@Client.on_message(filters.command("remove") & filters.private)
async def remove_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, keyboard = await select_project_keyboard("p_remove_confirm")
    if not keyboard:
        await message.reply_text(text)
    else:
        await message.reply_text("🗑 Select a project to remove:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^p_remove_confirm:(.+)"))
async def callback_remove_confirm(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_remove_confirm:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    confirm_text = (
        f"⚠️ Are you sure you want to remove:\n\n"
        f"Project: {project['project_name']}\n"
        f"ID: {project_id}\n\n"
        f"This will stop and remove the container, image, and all project data."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❌ Cancel", callback_data="p_page:1"),
            InlineKeyboardButton("✅ Confirm Remove", callback_data=f"p_remove_do:{project_id}")
        ]
    ])

    await callback_query.message.edit_text(confirm_text, reply_markup=keyboard)
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^p_remove_do:(.+)"))
async def callback_remove_do(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_remove_do:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    container_name = project.get("container_name")
    image_name = project.get("image_name")
    deployment_path = project.get("deployment_path")

    # Stop & remove container and image
    await DockerManager.remove_container_and_image(container_name, image_name)

    # Clean up deployment files
    if deployment_path and os.path.exists(deployment_path):
        import shutil
        try:
            shutil.rmtree(deployment_path)
        except Exception:
            pass

    # Delete record from database
    await Database.delete_project(project_id)

    await callback_query.message.edit_text(f"🗑 Project '{project['project_name']}' ({project_id}) removed successfully.")
    await callback_query.answer()
