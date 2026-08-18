import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter, mask_secret
from bot.utils.github_check import check_user_github_connection, GITHUB_AUTH_URL
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.docker_inspector import DockerInspector
from bot.utils.migration import execute_account_migration

logger = logging.getLogger(__name__)

SETTINGS_SESSIONS = {}
MIGRATION_SESSIONS = {}

def build_migration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    session = MIGRATION_SESSIONS.get(user_id, {})
    services = session.get("services", [])
    selected = session.get("selected", set())

    buttons = []
    for idx, item in enumerate(services):
        srv = item.get("service", item)
        srv_id = srv.get("id")
        srv_name = srv.get("name", "Service")
        checkbox = "☑️" if srv_id in selected else "🔲"
        buttons.append([InlineKeyboardButton(f"{checkbox} {srv_name}", callback_data=f"mig_toggle_{idx}")])

    select_all_label = "❌ Deselect All" if len(selected) == len(services) else "✅ Select All"
    buttons.append([
        InlineKeyboardButton(select_all_label, callback_data="mig_toggle_all"),
        InlineKeyboardButton("🚀 Done (Start Migration)", callback_data="mig_start")
    ])
    buttons.append([InlineKeyboardButton("❌ Skip Migration", callback_data="mig_skip")])

    return InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command("settings") & auth_filter)
async def settings_command(client: Client, message: Message):
    await show_settings_menu(client, message.chat.id, message.from_user.id)

@Client.on_callback_query(filters.regex("^open_settings$") & auth_filter)
async def settings_callback(client: Client, callback_query: CallbackQuery):
    await show_settings_menu(client, callback_query.message.chat.id, callback_query.from_user.id, callback_query.message)

async def show_settings_menu(client: Client, chat_id: int, user_id: int, message_to_edit: Message = None):
    current_key = await db.get_user_render_key(user_id)
    masked_key = mask_secret(current_key) if current_key else "Not Configured"

    current_gh_token = await db.get_user_github_token(user_id)
    masked_gh_token = mask_secret(current_gh_token) if current_gh_token else "Not Configured (Public Repos Only)"

    connected, _, _ = await check_user_github_connection(user_id)
    github_status = "✅ Connected & Valid" if connected else "⚠️ Action Required"

    text = (
        "⚙️ <b>Render Deployer Bot - Settings</b>\n\n"
        f"<b>Render API Key:</b> <code>{masked_key}</code>\n"
        f"<b>GitHub PAT Token:</b> <code>{masked_gh_token}</code>\n"
        f"<b>Render-GitHub Link:</b> {github_status}\n\n"
        "Configure your keys to manage public & private repositories on Render."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Update Render API Key", callback_data="update_api_key")],
        [InlineKeyboardButton("🐙 Connect GitHub Token (Private Repos)", callback_data="update_gh_token")],
        [InlineKeyboardButton("🔗 Connect GitHub Account to Render", url=GITHUB_AUTH_URL)],
        [InlineKeyboardButton("🔄 Verify Connection", callback_data="verify_github_conn")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ])

    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)

@Client.on_callback_query(filters.regex("^update_api_key$") & auth_filter)
async def update_key_prompt(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    SETTINGS_SESSIONS[user_id] = "AWAIT_KEY"

    await callback_query.message.edit_text(
        "🔑 <b>Update Render API Key</b>\n\n"
        "Please send your Render API Key (starts with <code>rnd_...</code>):\n"
        "<i>You can obtain your API Key from Render Dashboard -> Account Settings -> API Keys</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="open_settings")]
        ])
    )

@Client.on_callback_query(filters.regex("^update_gh_token$") & auth_filter)
async def update_gh_token_prompt(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    SETTINGS_SESSIONS[user_id] = "AWAIT_GH_TOKEN"

    await callback_query.message.edit_text(
        "🐙 <b>Connect GitHub Personal Access Token (PAT)</b>\n\n"
        "To allow the bot to list and deploy your **private GitHub repositories**, send your GitHub Token (starts with <code>ghp_...</code> or <code>github_pat_...</code>):\n"
        "<i>Create a token on GitHub Settings -> Developer settings -> Personal Access Tokens</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="open_settings")]
        ])
    )

# Global Auto-Detection Handler for Render API Key & GitHub Tokens sent anytime
@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter, group=-1)
async def auto_token_detector(client: Client, message: Message):
    user_id = message.from_user.id
    text_input = message.text.strip()

    # Check for Render API Key (rnd_...)
    if "rnd_" in text_input:
        new_key = [part for part in text_input.split() if part.startswith("rnd_")][0]
        try:
            render = RenderAPI(new_key)
            owner_id = await render.get_owner_id()
            if owner_id:
                old_key = await db.get_user_render_key(user_id)
                old_services = []

                if old_key and old_key != new_key:
                    try:
                        old_render = RenderAPI(old_key)
                        old_services = await old_render.list_services()
                    except Exception as e_old:
                        logger.warning(f"Failed to fetch services from old account: {e_old}")

                if old_services:
                    MIGRATION_SESSIONS[user_id] = {
                        "old_key": old_key,
                        "new_key": new_key,
                        "services": old_services,
                        "selected": set()
                    }
                    SETTINGS_SESSIONS.pop(user_id, None)
                    await message.reply_text(
                        "🔄 <b>New Render API Key Detected!</b>\n\n"
                        f"Found {len(old_services)} active service(s) on your old Render account.\n"
                        "Select the service(s) you want to migrate to your new Render account:\n"
                        "<i>Note: Old services will be suspended only after all selected services are deployed on the new account.</i>",
                        reply_markup=build_migration_keyboard(user_id)
                    )
                else:
                    await db.set_user_render_key(user_id, new_key)
                    await db.log_action(user_id, "AUTO_SAVE_RENDER_API_KEY", {})
                    SETTINGS_SESSIONS.pop(user_id, None)
                    await message.reply_text(
                        f"✅ <b>Render API Key detected, verified & saved!</b>\nKey: <code>{mask_secret(new_key)}</code>",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]])
                    )
                return
        except Exception as e:
            logger.warning(f"Auto-detect Render key validation failed: {e}")

    # Check for GitHub PAT Token (ghp_... or github_pat_...)
    if "ghp_" in text_input or "github_pat_" in text_input:
        token = [part for part in text_input.split() if part.startswith("ghp_") or part.startswith("github_pat_")][0]
        repos = await DockerInspector.fetch_user_repos("me", github_token=token)
        if repos is not None:
            await db.set_user_github_token(user_id, token)
            await db.log_action(user_id, "AUTO_SAVE_GITHUB_TOKEN", {})
            SETTINGS_SESSIONS.pop(user_id, None)

            await message.reply_text(
                f"✅ <b>GitHub Access Token detected, verified & saved!</b>\n"
                f"The bot can now access all {len(repos)} public and private repositories in your account.\nToken: <code>{mask_secret(token)}</code>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Start Deploy", callback_data="start_deploy")]])
            )
            return

    message.continue_propagation()

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter)
async def settings_key_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state = SETTINGS_SESSIONS.get(user_id)
    if not state:
        message.continue_propagation()
        return

    text_input = message.text.strip()

    if state == "AWAIT_KEY":
        try:
            new_key = text_input
            render = RenderAPI(new_key)
            owner_id = await render.get_owner_id()
            if not owner_id:
                await message.reply_text("❌ Could not authenticate with Render. Please check your API key.")
                return

            old_key = await db.get_user_render_key(user_id)
            old_services = []

            if old_key and old_key != new_key:
                try:
                    old_render = RenderAPI(old_key)
                    old_services = await old_render.list_services()
                except Exception as e_old:
                    logger.warning(f"Failed to fetch services from old account: {e_old}")

            if old_services:
                MIGRATION_SESSIONS[user_id] = {
                    "old_key": old_key,
                    "new_key": new_key,
                    "services": old_services,
                    "selected": set()
                }
                SETTINGS_SESSIONS.pop(user_id, None)
                await message.reply_text(
                    "🔄 <b>New Render API Key Verified!</b>\n\n"
                    f"Found {len(old_services)} active service(s) on your old Render account.\n"
                    "Select the service(s) you want to migrate to your new Render account:\n"
                    "<i>Note: Old services will be suspended only after all selected services are deployed on the new account.</i>",
                    reply_markup=build_migration_keyboard(user_id)
                )
            else:
                await db.set_user_render_key(user_id, new_key)
                await db.log_action(user_id, "UPDATE_RENDER_API_KEY", {})
                SETTINGS_SESSIONS.pop(user_id, None)
                await message.reply_text(
                    "✅ <b>Render API Key saved and verified successfully!</b>",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]])
                )

        except RenderAPIError as e:
            await message.reply_text(f"❌ Render API Key error: {e.message}")
        except Exception as e:
            await message.reply_text(f"❌ Error validating key: {str(e)}")

    elif state == "AWAIT_GH_TOKEN":
        repos = await DockerInspector.fetch_user_repos("me", github_token=text_input)
        if repos is not None:
            await db.set_user_github_token(user_id, text_input)
            await db.log_action(user_id, "UPDATE_GITHUB_TOKEN", {})
            SETTINGS_SESSIONS.pop(user_id, None)

            await message.reply_text(
                f"✅ <b>GitHub Access Token saved successfully!</b>\n"
                f"The bot can now access all {len(repos)} public and private repositories in your account.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]])
            )
        else:
            await message.reply_text("❌ Could not authenticate GitHub Token. Please check token permissions.")

@Client.on_callback_query(filters.regex("^mig_toggle_(\\d+)$") & auth_filter)
async def mig_toggle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    session = MIGRATION_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Migration session expired.", show_alert=True)
        return

    services = session.get("services", [])
    if 0 <= idx < len(services):
        srv = services[idx].get("service", services[idx])
        srv_id = srv.get("id")
        selected = session["selected"]
        if srv_id in selected:
            selected.remove(srv_id)
        else:
            selected.add(srv_id)

    await callback_query.message.edit_reply_markup(reply_markup=build_migration_keyboard(user_id))

@Client.on_callback_query(filters.regex("^mig_toggle_all$") & auth_filter)
async def mig_toggle_all_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = MIGRATION_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Migration session expired.", show_alert=True)
        return

    services = session.get("services", [])
    selected = session["selected"]

    all_ids = {s.get("service", s).get("id") for s in services}
    if len(selected) == len(all_ids):
        session["selected"] = set()
    else:
        session["selected"] = set(all_ids)

    await callback_query.message.edit_reply_markup(reply_markup=build_migration_keyboard(user_id))

@Client.on_callback_query(filters.regex("^mig_skip$") & auth_filter)
async def mig_skip_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = MIGRATION_SESSIONS.pop(user_id, None)
    if session and "new_key" in session:
        await db.set_user_render_key(user_id, session["new_key"])

    await callback_query.message.edit_text(
        "✅ <b>New Render API Key Saved!</b>\nMigration skipped.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]])
    )

@Client.on_callback_query(filters.regex("^mig_start$") & auth_filter)
async def mig_start_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = MIGRATION_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Migration session expired.", show_alert=True)
        return

    selected_ids = session.get("selected", set())
    if not selected_ids:
        await callback_query.answer("Please select at least one service to migrate.", show_alert=True)
        return

    old_key = session["old_key"]
    new_key = session["new_key"]
    all_services = session["services"]

    selected_services = [s for s in all_services if s.get("service", s).get("id") in selected_ids]

    msg = await callback_query.message.edit_text("⏳ <b>Starting migration... Creating services on new Render account...</b>")

    res = await execute_account_migration(old_key, new_key, user_id, selected_services)
    MIGRATION_SESSIONS.pop(user_id, None)

    deployed = res.get("deployed", [])
    suspended_count = res.get("suspended_count", 0)

    dm_lines = [
        "🎉 <b>Render Service Account Migration Completed!</b>\n",
        f"<b>Deployed on New Account:</b> {len(deployed)} service(s)",
        f"<b>Suspended on Old Account:</b> {suspended_count} service(s)\n",
        "<b>Newly Generated Service URLs:</b>"
    ]

    for item in deployed:
        dm_lines.append(f"• <b>{item['name']}:</b> {item['url']}")

    dm_text = "\n".join(dm_lines)

    await msg.edit_text(
        dm_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 View Projects", callback_data="list_projects")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]
        ])
    )

    # Also send to user's DM
    try:
        await client.send_message(user_id, dm_text)
    except Exception as e:
        logger.warning(f"Could not send migration DM to user {user_id}: {e}")
