import logging
from typing import Dict
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter, mask_secret, mask_env_vars
from bot.utils.render_api import RenderAPI, RenderAPIError

logger = logging.getLogger(__name__)

ENV_SESSIONS: Dict[int, Dict[str, str]] = {}

@Client.on_message(filters.command("env") & auth_filter)
async def env_command(client: Client, message: Message):
    user_id = message.from_user.id
    api_key = await db.get_user_render_key(user_id)
    if not api_key:
        await message.reply_text("🔑 Please configure your Render API Key in /settings first.")
        return

    render = RenderAPI(api_key)
    try:
        services = await render.list_services()
        if not services:
            await message.reply_text("📂 No Render services found.")
            return

        buttons = []
        for item in services:
            srv = item.get("service", item)
            buttons.append([InlineKeyboardButton(f"⚙️ {srv.get('name')}", callback_data=f"env_service_{srv.get('id')}")])

        await message.reply_text(
            "⚙️ <b>Environment Variables Manager</b>\nSelect a service to view/edit variables:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except RenderAPIError as e:
        await message.reply_text(f"❌ Error: {e.message}")

@Client.on_callback_query(filters.regex("^manage_env$") & auth_filter)
async def manage_env_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    if not api_key:
        await callback_query.message.edit_text("🔑 Please configure your Render API Key in /settings first.")
        return

    render = RenderAPI(api_key)
    try:
        services = await render.list_services()
        if not services:
            await callback_query.message.edit_text("📂 No Render services found.")
            return

        buttons = []
        for item in services:
            srv = item.get("service", item)
            buttons.append([InlineKeyboardButton(f"⚙️ {srv.get('name')}", callback_data=f"env_service_{srv.get('id')}")])

        await callback_query.message.edit_text(
            "⚙️ <b>Environment Variables Manager</b>\nSelect a service to view/edit variables:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except RenderAPIError as e:
        await callback_query.answer(f"Error: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^env_service_(.+)$") & auth_filter)
async def service_env_view(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        env_vars = await render.get_env_vars(srv_id)
        masked_vars = mask_env_vars(env_vars)

        lines = [f"⚙️ <b>Environment Variables for Service:</b> <code>{srv_id}</code>\n"]
        if not masked_vars:
            lines.append("<i>No environment variables configured.</i>")
        else:
            for k, v in masked_vars.items():
                lines.append(f"• <code>{k}</code> = <code>{v}</code>")

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Add/Edit Variable", callback_data=f"env_add_{srv_id}"),
                InlineKeyboardButton("📥 Bulk Import", callback_data=f"env_import_{srv_id}")
            ],
            [
                InlineKeyboardButton("🗑 Delete Variable", callback_data=f"env_del_{srv_id}"),
                InlineKeyboardButton("🔙 Back to Service", callback_data=f"view_service_{srv_id}")
            ]
        ])

        await callback_query.message.edit_text("\n".join(lines), reply_markup=kb)

    except RenderAPIError as e:
        await callback_query.answer(f"Failed to fetch env vars: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^env_add_(.+)$") & auth_filter)
async def env_add_prompt(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    ENV_SESSIONS[user_id] = {"service_id": srv_id, "action": "ADD"}

    await callback_query.message.edit_text(
        "➕ <b>Add/Edit Environment Variable</b>\n\n"
        "Send the variable in <code>KEY=value</code> format:\n"
        "<i>Example: DATABASE_URL=mongodb://...</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"env_service_{srv_id}")]
        ])
    )

@Client.on_callback_query(filters.regex("^env_import_(.+)$") & auth_filter)
async def env_import_prompt(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    ENV_SESSIONS[user_id] = {"service_id": srv_id, "action": "IMPORT"}

    await callback_query.message.edit_text(
        "📥 <b>Bulk Import Environment Variables</b>\n\n"
        "Send multiple variables separated by new lines in <code>KEY=value</code> format:\n"
        "<i>Example:\nPORT=8080\nNODE_ENV=production</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"env_service_{srv_id}")]
        ])
    )

@Client.on_callback_query(filters.regex("^env_del_(.+)$") & auth_filter)
async def env_del_prompt(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    ENV_SESSIONS[user_id] = {"service_id": srv_id, "action": "DELETE"}

    await callback_query.message.edit_text(
        "🗑 <b>Delete Environment Variable</b>\n\n"
        "Send the KEY name you wish to delete:\n"
        "<i>Example: DATABASE_URL</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"env_service_{srv_id}")]
        ])
    )

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter)
async def env_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = ENV_SESSIONS.get(user_id)
    if not session:
        message.continue_propagation()
        return

    srv_id = session["service_id"]
    action = session["action"]
    text = message.text.strip()

    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        current_vars = await render.get_env_vars(srv_id)

        if action in ["ADD", "IMPORT"]:
            for line in text.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    current_vars[k.strip()] = v.strip()

            await render.update_env_vars(srv_id, current_vars)
            await db.log_action(user_id, "UPDATE_ENV_VARS", {"service_id": srv_id, "action": action})
            ENV_SESSIONS.pop(user_id, None)

            await message.reply_text(
                "✅ <b>Environment variables updated successfully!</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Back to Env Vars", callback_data=f"env_service_{srv_id}")]])
            )

        elif action == "DELETE":
            key_to_del = text.strip()
            if key_to_del in current_vars:
                current_vars.pop(key_to_del)
                await render.update_env_vars(srv_id, current_vars)
                await db.log_action(user_id, "DELETE_ENV_VAR", {"service_id": srv_id, "key": key_to_del})
                ENV_SESSIONS.pop(user_id, None)

                await message.reply_text(
                    f"✅ <b>Deleted <code>{key_to_del}</code> successfully!</b>",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Back to Env Vars", callback_data=f"env_service_{srv_id}")]])
                )
            else:
                await message.reply_text(f"❌ Key <code>{key_to_del}</code> not found in environment variables.")

    except RenderAPIError as e:
        await message.reply_text(f"❌ Failed to update env vars: {e.message}")
