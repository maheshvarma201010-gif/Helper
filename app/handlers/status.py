import logging
import math
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import Config
from app.database import Database
from app.services.docker_manager import DockerManager
from app.services.env_manager import EnvManager

logger = logging.getLogger(__name__)

PROJECTS_PER_PAGE = 5

async def build_status_page(page: int = 1):
    projects = await Database.get_all_projects()
    if not projects:
        return "📊 PROJECT STATUS\n\nNo projects found. Use /deploy to create one.", None

    total_projects = len(projects)
    total_pages = math.ceil(total_projects / PROJECTS_PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * PROJECTS_PER_PAGE
    page_projects = projects[start_idx : start_idx + PROJECTS_PER_PAGE]

    lines = ["📊 PROJECT STATUS\n"]
    buttons = []

    for proj in page_projects:
        p_id = proj["project_id"]
        p_name = proj["project_name"]
        c_name = proj.get("container_name", f"telegram-project-{p_id}")

        # Check actual status from docker engine if available
        docker_status = await DockerManager.inspect_status(c_name)
        status_str = proj.get("status", "UNKNOWN")
        if docker_status != "UNKNOWN (DOCKER UNAVAILABLE)":
            status_str = docker_status

        status_emoji = "🟢" if status_str in ("RUNNING", "RUNNING") else ("🟡" if status_str == "PAUSED" else "🔴")

        lines.append(
            f"{status_emoji} Project\n"
            f"━━━━━━━━━━━━━━\n"
            f"📦 Name: {p_name}\n"
            f"🆔 ID: {p_id}\n"
            f"🐳 Container: {c_name}\n"
            f"📌 Status: {status_str}\n"
        )

        row1 = [
            InlineKeyboardButton("📊 Details", callback_data=f"p_details:{p_id}"),
            InlineKeyboardButton("📜 Logs", callback_data=f"p_logs:{p_id}"),
            InlineKeyboardButton("🔄 Restart", callback_data=f"p_restart:{p_id}")
        ]
        row2 = [
            InlineKeyboardButton("⏸ Pause", callback_data=f"p_pause:{p_id}"),
            InlineKeyboardButton("▶️ Start", callback_data=f"p_start:{p_id}"),
            InlineKeyboardButton("📦 Replace ZIP", callback_data=f"sel_replace:{p_id}")
        ]
        row3 = [
            InlineKeyboardButton("⚙️ ENV", callback_data=f"p_env:{p_id}"),
            InlineKeyboardButton("🚀 Redeploy", callback_data=f"p_redeploy:{p_id}"),
            InlineKeyboardButton("🗑 Remove", callback_data=f"p_remove_confirm:{p_id}")
        ]
        buttons.extend([row1, row2, row3])

    # Navigation buttons
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"p_page:{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="p_noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"p_page:{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    return "\n".join(lines), InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    text, reply_markup = await build_status_page(page=1)
    await message.reply_text(text, reply_markup=reply_markup)

@Client.on_callback_query(filters.regex(r"^p_page:(\d+)"))
async def callback_status_page(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    page = int(callback_query.data.split("p_page:")[1])
    text, reply_markup = await build_status_page(page=page)
    await callback_query.message.edit_text(text, reply_markup=reply_markup)
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^p_details:(.+)"))
async def callback_project_details(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("p_details:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    c_name = project.get("container_name", f"telegram-project-{project_id}")
    docker_status = await DockerManager.inspect_status(c_name)
    status_str = docker_status if docker_status != "UNKNOWN (DOCKER UNAVAILABLE)" else project.get("status", "UNKNOWN")

    last_error = project.get("last_error") or "None"

    details_text = (
        f"📊 PROJECT DETAILS\n\n"
        f"📦 Project Name: {project.get('project_name')}\n"
        f"🆔 Project ID: {project.get('project_id')}\n"
        f"🐳 Image: {project.get('image_name')}\n"
        f"📦 Container: {c_name}\n"
        f"📌 Status: {status_str}\n"
        f"🕐 Created: {project.get('created_at')}\n"
        f"🔄 Last Updated: {project.get('updated_at')}\n"
        f"📁 Source: {project.get('zip_filename')}\n"
        f"❌ Last Error: {last_error}\n"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Status", callback_data="p_page:1")]
    ])

    await callback_query.message.edit_text(details_text, reply_markup=keyboard)
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^p_noop$"))
async def callback_noop(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
