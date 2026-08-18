import logging
import aiohttp
from typing import Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.docker_inspector import DockerInspector
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.handlers.deploy import DEPLOY_SESSIONS, fetch_and_show_branches

logger = logging.getLogger(__name__)

# Sessions for /create_repo flow
# Schema: {user_id: {"mode": "IMPORT"|"CREATE", "step": str, ...}}
CREATE_REPO_SESSIONS: Dict[int, Dict[str, Any]] = {}

def get_create_repo_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Import Repository", callback_data="create_repo_mode_import"),
            InlineKeyboardButton("➕ Create Repository", callback_data="create_repo_mode_create")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
    ])

@Client.on_message(filters.command("create_repo") & auth_filter)
async def create_repo_command(client: Client, message: Message):
    user_id = message.from_user.id
    CREATE_REPO_SESSIONS[user_id] = {"step": "CHOICE"}

    await message.reply_text(
        "🛠 <b>Repository & Deployment Wizard (/create_repo)</b>\n\n"
        "Would you like to <b>Import</b> an existing repository or <b>Create</b> a brand new repository?",
        reply_markup=get_create_repo_choice_keyboard()
    )

@Client.on_callback_query(filters.regex("^create_repo_mode_(import|create)$") & auth_filter)
async def create_repo_mode_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    mode = callback_query.matches[0].group(1).upper()

    session = {"mode": mode, "env_vars": {}}
    CREATE_REPO_SESSIONS[user_id] = session

    if mode == "IMPORT":
        session["step"] = "IMPORT_AWAIT_REPO_URL"
        await callback_query.message.edit_text(
            "📥 <b>Import Repository (1/4)</b>\n\n"
            "Please send the GitHub repository URL or name:\n"
            "<i>Examples: https://github.com/owner/repo OR owner/repo</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
            ])
        )
    else:  # CREATE
        session["step"] = "CREATE_AWAIT_REPO_NAME"
        await callback_query.message.edit_text(
            "➕ <b>Create New Repository (1/2)</b>\n\n"
            "Please enter the name for your new GitHub repository:\n"
            "<i>Example: my-awesome-app</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
            ])
        )

@Client.on_callback_query(filters.regex("^cancel_create_repo$") & auth_filter)
async def cancel_create_repo_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    CREATE_REPO_SESSIONS.pop(user_id, None)
    await callback_query.message.edit_text("❌ Repository creation/import flow canceled.")

async def create_github_repo(repo_name: str, github_token: str, private: bool = False) -> Optional[Dict[str, Any]]:
    """Creates a new repository on GitHub for the authenticated user using GitHub REST API."""
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"Bearer {github_token.strip()}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RenderDeployerBot"
    }
    payload = {
        "name": repo_name,
        "private": private,
        "auto_init": True  # Initializes with README so default branch exists
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=15) as resp:
                data = await resp.json()
                if resp.status in [200, 201]:
                    return data
                else:
                    err_msg = data.get("message", str(data)) if isinstance(data, dict) else str(data)
                    logger.warning(f"Failed to create GitHub repo: HTTP {resp.status} - {err_msg}")
                    return None
        except Exception as e:
            logger.error(f"Error calling GitHub create repo API: {e}")
            return None

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "create_repo", "repos", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter, group=1)
async def create_repo_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = CREATE_REPO_SESSIONS.get(user_id)
    if not session:
        message.continue_propagation()
        return

    step = session.get("step")
    text = message.text.strip()
    gh_token = await db.get_user_github_token(user_id)

    # ---------------- IMPORT FLOW ----------------
    if step == "IMPORT_AWAIT_REPO_URL":
        parsed = DockerInspector.parse_github_url(text)
        if not parsed:
            await message.reply_text("❌ Invalid repository URL or format. Please send in format: <code>owner/repo</code> or <code>https://github.com/owner/repo</code>")
            return

        owner, repo_short = parsed
        session["owner"] = owner
        session["repo_name"] = repo_short
        session["repo"] = f"https://github.com/{owner}/{repo_short}"
        session["step"] = "IMPORT_AWAIT_BRANCH"

        # Show branch selection
        msg = await message.reply_text(f"🔍 Fetching branches for <code>{owner}/{repo_short}</code>...")
        branches = await DockerInspector.fetch_repo_branches(owner, repo_short, github_token=gh_token)

        if not branches:
            await msg.edit_text(
                f"❌ <b>Could not fetch branches for {owner}/{repo_short}.</b>\n\n"
                f"Please verify repository permissions or check your GitHub token in /settings.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
                ])
            )
            return

        session["fetched_branches"] = branches
        total_branches = len(branches)
        buttons = []
        row = []
        for b in branches[:10]:
            row.append(InlineKeyboardButton(f"🌿 {b}", callback_data=f"cr_import_branch_{b}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")])
        await msg.edit_text(
            f"📥 <b>Import Repository (2/4)</b>\n"
            f"Select branch for <code>{owner}/{repo_short}</code> ({total_branches} branches found):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif step == "IMPORT_AWAIT_SERVICE_NAME":
        service_name = text
        session["service_name"] = service_name
        session["step"] = "AWAIT_ENV_VARS"

        await message.reply_text(
            f"✅ Service Name: <code>{service_name}</code>\n\n"
            "⚙️ <b>Environment Variables (Optional):</b>\n"
            "Send environment variables in <code>KEY=value</code> format (one per line).\n"
            "Or click 'Skip Env Vars' to proceed directly to Render deployment.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_cr_env_vars")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
            ])
        )

    # ---------------- CREATE FLOW ----------------
    elif step == "CREATE_AWAIT_REPO_NAME":
        repo_name = text
        session["repo_name"] = repo_name

        if not gh_token:
            await message.reply_text(
                "🐙 <b>GitHub Personal Access Token Required</b>\n\n"
                "To create a new repository directly on GitHub, please add your GitHub PAT in /settings.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
                ])
            )
            return

        msg = await message.reply_text(f"⏳ Creating repository <code>{repo_name}</code> on GitHub...")
        created_repo = await create_github_repo(repo_name, gh_token, private=False)

        if not created_repo:
            await msg.edit_text(
                f"❌ <b>Failed to create repository '{repo_name}' on GitHub.</b>\n"
                f"Check that your GitHub PAT has 'repo' scope and that the repository name is available.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
                ])
            )
            return

        full_name = created_repo.get("full_name", repo_name)
        html_url = created_repo.get("html_url", f"https://github.com/{full_name}")
        owner = full_name.split("/")[0] if "/" in full_name else "user"

        session["owner"] = owner
        session["repo"] = html_url
        session["branch"] = created_repo.get("default_branch", "main")
        session["service_name"] = repo_name
        session["step"] = "AWAIT_ENV_VARS"

        await msg.edit_text(
            f"✅ <b>Repository Created Successfully on GitHub!</b>\n\n"
            f"<b>Repository:</b> <code>{full_name}</code>\n"
            f"<b>URL:</b> {html_url}\n\n"
            "⚙️ <b>Environment Variables (Optional):</b>\n"
            "Send environment variables in <code>KEY=value</code> format (one per line).\n"
            "Or click 'Skip Env Vars' to proceed directly to Render deployment.",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_cr_env_vars")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
            ])
        )

    elif step == "AWAIT_ENV_VARS":
        parsed_vars = {}
        for line in text.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                parsed_vars[k.strip()] = v.strip()
        session["env_vars"].update(parsed_vars)
        session["step"] = "STARTING"
        await start_import_process(client, message.chat.id, user_id, session)

@Client.on_callback_query(filters.regex("^skip_cr_env_vars$") & auth_filter)
async def skip_cr_env_vars_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = CREATE_REPO_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /create_repo again.")
        return

    session["step"] = "STARTING"
    await callback_query.message.edit_text("⏳ <b>Starting deployment to Render...</b>")
    await start_create_import_deployment(client, callback_query.message.chat.id, user_id, session)

@Client.on_callback_query(filters.regex("^cr_import_branch_(.+)$") & auth_filter)
async def cr_import_branch_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    branch = callback_query.matches[0].group(1).strip()
    session = CREATE_REPO_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /create_repo again.")
        return

    session["branch"] = branch
    session["step"] = "IMPORT_AWAIT_SERVICE_NAME"

    await callback_query.message.edit_text(
        f"✅ Selected Branch: <code>{branch}</code>\n\n"
        f"📥 <b>Import Repository (3/4)</b>\n"
        f"Please enter the name for your service/repository deployment:\n"
        f"<i>Example: {session.get('repo_name', 'my-app')}</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create_repo")]
        ])
    )

async def start_import_process(client: Client, chat_id: int, user_id: int, session: Dict[str, Any]):
    msg = await client.send_message(chat_id, "⏳ <b>Starting repository import and setup...</b>")
    await start_create_import_deployment(client, chat_id, user_id, session, message_to_edit=msg)

async def start_create_import_deployment(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    owner = session["owner"]
    repo_name = session["repo_name"]
    branch = session.get("branch", "main")
    service_name = session.get("service_name", repo_name)
    repo_url = session["repo"]

    render_key = await db.get_user_render_key(user_id)
    if not render_key:
        text = (
            "🔑 <b>Render API Key Required</b>\n\n"
            "Please configure your Render API Key in /settings to complete service deployment."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]])
        if message_to_edit:
            await message_to_edit.edit_text(text, reply_markup=kb)
        else:
            await client.send_message(chat_id, text, reply_markup=kb)
        return

    render = RenderAPI(render_key)
    gh_token = await db.get_user_github_token(user_id)

    # Check for Dockerfile in repo
    detected_df = await DockerInspector.detect_dockerfiles(owner, repo_name, branch=branch, github_token=gh_token)
    is_docker = len(detected_df) > 0
    dockerfilePath = detected_df[0] if is_docker else "./Dockerfile"

    deploy_config = {
        "name": service_name,
        "repo": repo_url,
        "branch": branch,
        "type": "web_service",
        "is_docker": is_docker,
        "dockerfilePath": dockerfilePath,
        "dockerContext": ".",
        "instance_type": session.get("instance_type", "free"),
        "env_vars": session.get("env_vars", {})
    }

    try:
        res = await render.create_service(deploy_config)
        srv = res.get("service", res)
        srv_id = srv.get("id")
        srv_name = srv.get("name")
        srv_url = srv.get("serviceDetails", {}).get("url", "")

        await db.save_deployment(
            user_id=user_id,
            service_id=srv_id,
            service_name=srv_name,
            repo_url=repo_url,
            branch=branch,
            service_type="web_service",
            is_docker=is_docker,
            status="created",
            service_url=srv_url
        )

        await db.log_action(user_id, "CREATE_REPO_DEPLOYMENT", {"service_id": srv_id, "repo": repo_url})
        CREATE_REPO_SESSIONS.pop(user_id, None)

        text = (
            f"🎉 <b>Repository Creation / Import Completed Successfully!</b>\n\n"
            f"<b>Service Name:</b> {srv_name}\n"
            f"<b>Service ID:</b> <code>{srv_id}</code>\n"
            f"<b>Repository:</b> <code>{owner}/{repo_name}</code>\n"
            f"<b>Branch:</b> <code>{branch}</code>\n"
        )
        if srv_url:
            text += f"<b>URL:</b> {srv_url}\n"

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📜 View Logs", callback_data=f"logs_{srv_id}"),
                InlineKeyboardButton("📊 Status", callback_data=f"status_{srv_id}")
            ],
            [InlineKeyboardButton("📂 All Projects", callback_data="list_projects")]
        ])

        if message_to_edit:
            await message_to_edit.edit_text(text, reply_markup=kb)
        else:
            await client.send_message(chat_id, text, reply_markup=kb)

    except RenderAPIError as e:
        err_msg = f"❌ <b>Render Service Creation Error:</b> {e.message}"
        if message_to_edit:
            await message_to_edit.edit_text(err_msg)
        else:
            await client.send_message(chat_id, err_msg)
    except Exception as e:
        logger.error(f"Error in start_create_import_deployment: {e}")
        err_msg = f"❌ <b>Error:</b> {str(e)}"
        if message_to_edit:
            await message_to_edit.edit_text(err_msg)
        else:
            await client.send_message(chat_id, err_msg)
