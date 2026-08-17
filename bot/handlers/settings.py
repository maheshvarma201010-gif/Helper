import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter, mask_secret
from bot.utils.github_check import check_user_github_connection, GITHUB_AUTH_URL
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.docker_inspector import DockerInspector

logger = logging.getLogger(__name__)

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
        key = [part for part in text_input.split() if part.startswith("rnd_")][0]
        try:
            render = RenderAPI(key)
            owner_id = await render.get_owner_id()
            if owner_id:
                await db.set_user_render_key(user_id, key)
                await db.log_action(user_id, "AUTO_SAVE_RENDER_API_KEY", {})
                SETTINGS_SESSIONS.pop(user_id, None)

                old_deploys = await db.get_user_deployments(user_id)
                if old_deploys:
                    count = len(old_deploys)
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Resync & Deploy All Old Repos", callback_data="resync_old_repos")],
                        [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
                    ])
                    await message.reply_text(
                        f"✅ <b>Render API Key detected, verified & saved!</b>\n\n"
                        f"ℹ️ <b>Found {count} previously deployed repository(s) in your history.</b>\n"
                        f"Would you like to re-deploy all these old repos to your new Render account?",
                        reply_markup=kb
                    )
                else:
                    await message.reply_text(
                        f"✅ <b>Render API Key detected, verified & saved!</b>\nKey: <code>{mask_secret(key)}</code>",
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
            render = RenderAPI(text_input)
            owner_id = await render.get_owner_id()
            if not owner_id:
                await message.reply_text("❌ Could not authenticate with Render. Please check your API key.")
                return

            await db.set_user_render_key(user_id, text_input)
            await db.log_action(user_id, "UPDATE_RENDER_API_KEY", {})
            SETTINGS_SESSIONS.pop(user_id, None)

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
