import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter, mask_secret
from bot.utils.github_check import check_user_github_connection, GITHUB_AUTH_URL
from bot.utils.render_api import RenderAPI, RenderAPIError

logger = logging.getLogger(__name__)

# User state for settings key entry: {user_id: "AWAIT_KEY"}
SETTINGS_SESSIONS = {}

@Client.on_message(filters.command("settings") & auth_filter)
async def settings_command(client: Client, message: Message):
    await show_settings_menu(client, message.chat.id, message.from_user.id)

@Client.on_callback_query(filters.regex("^open_settings$") & auth_filter)
async def settings_callback(client: Client, callback_query: CallbackQuery):
    await show_settings_menu(client, callback_query.message.chat.id, callback_query.from_user.id, callback_query.message)

async def show_settings_menu(client: Client, chat_id: int, user_id: int, message_to_edit: Message = None):
    current_key = await db.get_user_render_key(user_id)
    masked_key = mask_secret(current_key) if current_key else "Not Configured"

    connected, _, _ = await check_user_github_connection(user_id)
    github_status = "✅ Connected & Valid" if connected else "⚠️ Action Required"

    text = (
        "⚙️ <b>Render Deployer Bot - Settings</b>\n\n"
        f"<b>Render API Key:</b> <code>{masked_key}</code>\n"
        f"<b>GitHub/Render Status:</b> {github_status}\n\n"
        "Configure your personal Render API Key to manage services safely."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Update Render API Key", callback_data="update_api_key")],
        [InlineKeyboardButton("🔗 Connect GitHub Account", url=GITHUB_AUTH_URL)],
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

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter)
async def settings_key_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if SETTINGS_SESSIONS.get(user_id) != "AWAIT_KEY":
        return

    new_key = message.text.strip()

    try:
        render = RenderAPI(new_key)
        owner_id = await render.get_owner_id()
        if not owner_id:
            await message.reply_text("❌ Could not authenticate with Render. Please check your API key.")
            return

        await db.set_user_render_key(user_id, new_key)
        await db.log_action(user_id, "UPDATE_RENDER_API_KEY", {})
        SETTINGS_SESSIONS.pop(user_id, None)

        # Check for previously deployed repos in history
        old_deploys = await db.get_user_deployments(user_id)
        if old_deploys:
            count = len(old_deploys)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Resync & Deploy All Old Repos", callback_data="resync_old_repos")],
                [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
            ])
            await message.reply_text(
                f"✅ <b>Render API Key verified and saved!</b>\n\n"
                f"ℹ️ <b>Found {count} previously deployed repository(s) in your history.</b>\n"
                f"Would you like to re-deploy all these old repos to your new Render account?",
                reply_markup=kb
            )
        else:
            await message.reply_text(
                "✅ <b>Render API Key saved and verified successfully!</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]])
            )

    except RenderAPIError as e:
        await message.reply_text(f"❌ Render API Key error: {e.message}")
    except Exception as e:
        await message.reply_text(f"❌ Error validating key: {str(e)}")

@Client.on_callback_query(filters.regex("^resync_old_repos$") & auth_filter)
async def resync_old_repos_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    old_deploys = await db.get_user_deployments(user_id)
    if not old_deploys:
        await callback_query.answer("No old deployments found.", show_alert=True)
        return

    msg = await callback_query.message.edit_text("⏳ <b>Resynced API key. Deploying old repositories to new Render account...</b>")
    deployed_count = 0

    for record in old_deploys:
        try:
            config = {
                "name": record.get("service_name"),
                "repo": record.get("repo_url"),
                "branch": record.get("branch", "main"),
                "type": record.get("service_type", "web_service"),
                "is_docker": record.get("is_docker", False),
                "dockerfilePath": "./Dockerfile",
                "dockerContext": "."
            }
            res = await render.create_service(config)
            srv = res.get("service", res)
            srv_id = srv.get("id")
            await db.save_deployment(
                user_id=user_id,
                service_id=srv_id,
                service_name=record.get("service_name"),
                repo_url=record.get("repo_url"),
                branch=record.get("branch", "main"),
                service_type=record.get("service_type", "web_service"),
                is_docker=record.get("is_docker", False),
                status="created"
            )
            deployed_count += 1
        except Exception as e:
            logger.warning(f"Resync deployment error for {record.get('service_name')}: {e}")

    await msg.edit_text(
        f"✅ <b>Resync Complete!</b>\n\nSuccessfully deployed {deployed_count} old repositories to your new Render account.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 View Projects", callback_data="list_projects")]])
    )
