import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import Config
from app.database import Database
from app.handlers.deploy import USER_STATE

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("replace") & filters.private)
async def replace_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not Config.is_authorized(user_id):
        await message.reply_text("❌ You are not authorized to use this bot.")
        return

    projects = await Database.get_all_projects()
    if not projects:
        await message.reply_text("📦 No projects found. Use /deploy to deploy a project first.")
        return

    buttons = []
    for proj in projects:
        p_id = proj["project_id"]
        p_name = proj["project_name"]
        buttons.append([InlineKeyboardButton(f"📦 {p_name} ({p_id})", callback_data=f"sel_replace:{p_id}")])

    keyboard = InlineKeyboardMarkup(buttons)
    await message.reply_text("📦 Select the project you want to replace:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex(r"^sel_replace:(.+)"))
async def callback_select_replace(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not Config.is_authorized(user_id):
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return

    project_id = callback_query.data.split("sel_replace:")[1]
    project = await Database.get_project(project_id)
    if not project:
        await callback_query.answer("❌ Project not found.", show_alert=True)
        return

    USER_STATE[user_id] = {"action": "replace", "project_id": project_id}
    await callback_query.message.edit_text(
        f"📤 Send the new ZIP file for project:\n\n"
        f"📦 Project: {project['project_name']}\n"
        f"🆔 ID: {project_id}\n\n"
        f"The ZIP must contain a Dockerfile."
    )
    await callback_query.answer()
