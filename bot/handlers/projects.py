import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.github_check import check_user_github_connection
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.formatter import format_service_card

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("projects") & auth_filter)
async def list_projects_command(client: Client, message: Message):
    await display_projects_list(client, message.chat.id, message.from_user.id)

@Client.on_callback_query(filters.regex("^list_projects$") & auth_filter)
async def list_projects_callback(client: Client, callback_query: CallbackQuery):
    await display_projects_list(client, callback_query.message.chat.id, callback_query.from_user.id, callback_query.message)

async def display_projects_list(client: Client, chat_id: int, user_id: int, message_to_edit: Message = None):
    connected, error_msg, keyboard = await check_user_github_connection(user_id)
    if not connected:
        if message_to_edit:
            await message_to_edit.edit_text(error_msg, reply_markup=keyboard)
        else:
            await client.send_message(chat_id, error_msg, reply_markup=keyboard)
        return

    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        services = await render.list_services()
        if not services:
            text = "📂 <b>No Render services found.</b>\nUse /deploy to create a new service."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Deploy New Service", callback_data="start_deploy")]])
        else:
            text = "📂 <b>Your Render Services:</b>\nSelect a service to manage:"
            buttons = []
            for item in services:
                srv = item.get("service", item)
                srv_id = srv.get("id")
                srv_name = srv.get("name")
                buttons.append([InlineKeyboardButton(f"📦 {srv_name}", callback_data=f"view_service_{srv_id}")])
            buttons.append([InlineKeyboardButton("🚀 Deploy New", callback_data="start_deploy")])
            buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
            kb = InlineKeyboardMarkup(buttons)

        if message_to_edit:
            await message_to_edit.edit_text(text, reply_markup=kb)
        else:
            await client.send_message(chat_id, text, reply_markup=kb)

    except RenderAPIError as e:
        err = f"❌ <b>Render API Error:</b> {e.message}"
        if message_to_edit:
            await message_to_edit.edit_text(err)
        else:
            await client.send_message(chat_id, err)

@Client.on_callback_query(filters.regex("^view_service_(.+) $") & auth_filter)
@Client.on_callback_query(filters.regex("^view_service_(.+)$") & auth_filter)
async def view_service_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        service = await render.get_service(srv_id)
        deploys = await render.list_deploys(srv_id, limit=1)
        last_deploy = deploys[0] if deploys else None

        card_text = format_service_card(service, last_deploy)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"view_service_{srv_id}"),
                InlineKeyboardButton("📜 Logs", callback_data=f"logs_{srv_id}")
            ],
            [
                InlineKeyboardButton("🚀 Redeploy", callback_data=f"redeploy_{srv_id}"),
                InlineKeyboardButton("🔁 Restart", callback_data=f"restart_{srv_id}")
            ],
            [
                InlineKeyboardButton("⏸ Suspend", callback_data=f"suspend_{srv_id}"),
                InlineKeyboardButton("▶️ Resume", callback_data=f"resume_{srv_id}")
            ],
            [
                InlineKeyboardButton("⚙️ Env Vars", callback_data=f"env_service_{srv_id}"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"delete_confirm_{srv_id}")
            ],
            [InlineKeyboardButton("📂 All Projects", callback_data="list_projects")]
        ])

        await callback_query.message.edit_text(card_text, reply_markup=kb)
    except RenderAPIError as e:
        await callback_query.answer(f"Error: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^redeploy_(.+)$") & auth_filter)
async def redeploy_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        await render.redeploy_service(srv_id)
        await db.log_action(user_id, "REDEPLOY_SERVICE", {"service_id": srv_id})
        await callback_query.answer("🚀 Deployment triggered successfully!", show_alert=True)
    except RenderAPIError as e:
        await callback_query.answer(f"Redeploy failed: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^restart_(.+)$") & auth_filter)
async def restart_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        await render.restart_service(srv_id)
        await db.log_action(user_id, "RESTART_SERVICE", {"service_id": srv_id})
        await callback_query.answer("🔁 Restart signal sent!", show_alert=True)
    except RenderAPIError as e:
        await callback_query.answer(f"Restart failed: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^suspend_(.+)$") & auth_filter)
async def suspend_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        await render.suspend_service(srv_id)
        await db.log_action(user_id, "SUSPEND_SERVICE", {"service_id": srv_id})
        await callback_query.answer("⏸ Service suspended.", show_alert=True)
    except RenderAPIError as e:
        await callback_query.answer(f"Suspend failed: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^resume_(.+)$") & auth_filter)
async def resume_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        await render.resume_service(srv_id)
        await db.log_action(user_id, "RESUME_SERVICE", {"service_id": srv_id})
        await callback_query.answer("▶️ Service resumed.", show_alert=True)
    except RenderAPIError as e:
        await callback_query.answer(f"Resume failed: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^delete_confirm_(.+)$") & auth_filter)
async def delete_confirm_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ YES, DELETE PERMANENTLY", callback_data=f"delete_do_{srv_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"view_service_{srv_id}")
        ]
    ])
    await callback_query.message.edit_text(
        f"⚠️ <b>ARE YOU SURE YOU WANT TO DELETE THIS SERVICE?</b>\n\n"
        f"Service ID: <code>{srv_id}</code>\n"
        f"This action cannot be undone!",
        reply_markup=kb
    )

@Client.on_callback_query(filters.regex("^delete_do_(.+)$") & auth_filter)
async def delete_execute_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        await render.delete_service(srv_id)
        await db.remove_deployment(user_id, srv_id)
        await db.log_action(user_id, "DELETE_SERVICE", {"service_id": srv_id})
        await callback_query.message.edit_text(
            "🗑 <b>Service deleted successfully.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 All Projects", callback_data="list_projects")]])
        )
    except RenderAPIError as e:
        await callback_query.answer(f"Delete failed: {e.message}", show_alert=True)

@Client.on_callback_query(filters.regex("^logs_(.+)$") & auth_filter)
async def logs_callback(client: Client, callback_query: CallbackQuery):
    srv_id = callback_query.matches[0].group(1).strip()
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    try:
        deploys = await render.list_deploys(srv_id, limit=3)
        if not deploys:
            await callback_query.answer("No deployment logs found.", show_alert=True)
            return

        logs_summary = [f"📜 <b>Recent Deployment Logs for {srv_id}:</b>\n"]
        for d in deploys:
            d_id = d.get("id", "N/A")
            status = d.get("status", "N/A")
            created = d.get("createdAt", "N/A")
            logs_summary.append(f"• Deploy ID: <code>{d_id}</code> | Status: {status} | Time: {created[:19]}")

        await callback_query.message.edit_text(
            "\n".join(logs_summary),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Logs", callback_data=f"logs_{srv_id}")],
                [InlineKeyboardButton("🔙 Back to Service", callback_data=f"view_service_{srv_id}")]
            ])
        )
    except RenderAPIError as e:
        await callback_query.answer(f"Logs failed: {e.message}", show_alert=True)
