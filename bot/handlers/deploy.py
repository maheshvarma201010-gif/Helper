import logging
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.github_check import check_user_github_connection
from bot.utils.docker_inspector import DockerInspector
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.formatter import format_deployment_preview

logger = logging.getLogger(__name__)

# Temporary deployment wizard state per user: {user_id: dict_config}
DEPLOY_SESSIONS: Dict[int, Dict[str, Any]] = {}

def get_deployment_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐳 Deploy with Dockerfile", callback_data="deploy_mode_docker")],
        [InlineKeyboardButton("🛠 Standard Deploy (Build/Start)", callback_data="deploy_mode_standard")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])

def get_service_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Web Service", callback_data="srvtype_web_service"),
            InlineKeyboardButton("⚙️ Worker", callback_data="srvtype_background_worker")
        ],
        [
            InlineKeyboardButton("⏱ Cron Job", callback_data="srvtype_cron_job"),
            InlineKeyboardButton("📄 Static Site", callback_data="srvtype_static_site")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])

@Client.on_message(filters.command("deploy") & auth_filter)
async def deploy_command(client: Client, message: Message):
    user_id = message.from_user.id

    connected, error_msg, keyboard = await check_user_github_connection(user_id)
    if not connected:
        await message.reply_text(error_msg, reply_markup=keyboard)
        return

    DEPLOY_SESSIONS[user_id] = {"step": "SELECT_MODE", "env_vars": {}}

    await message.reply_text(
        "🚀 <b>New Deployment</b>\n\n"
        "Choose deployment method:\n\n"
        "• <b>🐳 Deploy with Dockerfile:</b> Uses repository Dockerfile. "
        "<b>Will NOT ask for Build/Start commands.</b>\n"
        "• <b>🛠 Standard Deploy:</b> Build Command + Start Command.",
        reply_markup=get_deployment_type_keyboard()
    )

@Client.on_callback_query(filters.regex("^start_deploy$") & auth_filter)
async def start_deploy_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    connected, error_msg, keyboard = await check_user_github_connection(user_id)
    if not connected:
        await callback_query.message.edit_text(error_msg, reply_markup=keyboard)
        return

    DEPLOY_SESSIONS[user_id] = {"step": "SELECT_MODE", "env_vars": {}}
    await callback_query.message.edit_text(
        "🚀 <b>New Deployment</b>\n\n"
        "Choose deployment method:\n\n"
        "• <b>🐳 Deploy with Dockerfile:</b> Uses repository Dockerfile. "
        "<b>Will NOT ask for Build/Start commands.</b>\n"
        "• <b>🛠 Standard Deploy:</b> Build Command + Start Command.",
        reply_markup=get_deployment_type_keyboard()
    )

@Client.on_callback_query(filters.regex("^deploy_mode_(docker|standard)$") & auth_filter)
async def deploy_mode_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    mode = callback_query.matches[0].group(1)

    session = DEPLOY_SESSIONS.get(user_id, {})
    session["is_docker"] = (mode == "docker")
    session["step"] = "AWAIT_REPO"
    DEPLOY_SESSIONS[user_id] = session

    mode_title = "🐳 Dockerfile Deployment" if session["is_docker"] else "🛠 Standard Deployment"
    await callback_query.message.edit_text(
        f"<b>{mode_title}</b>\n\n"
        "Please send GitHub Owner / Repo URL or GitHub Username:\n"
        "<i>Examples: https://github.com/owner/repository OR just owner_username</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
        ])
    )

@Client.on_callback_query(filters.regex("^srvtype_(web_service|background_worker|cron_job|static_site)$") & auth_filter)
async def service_type_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    srv_type = callback_query.matches[0].group(1)

    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /deploy again.")
        return

    session["type"] = srv_type
    session["step"] = "AWAIT_SERVICE_NAME"
    DEPLOY_SESSIONS[user_id] = session

    await callback_query.message.edit_text(
        f"<b>Service Type:</b> {srv_type}\n\n"
        "Please enter a unique Service Name:\n"
        "<i>Example: my-app-api</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
        ])
    )

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter)
async def wizard_text_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    step = session.get("step")
    text = message.text.strip()

    if step == "AWAIT_REPO":
        parsed = DockerInspector.parse_github_url(text)
        if parsed:
            owner, repo_name = parsed
            session["repo"] = text
            session["owner"] = owner
            session["repo_name"] = repo_name
            await fetch_and_show_branches(client, message.chat.id, user_id, session)
        else:
            # Treat text as username to list available repos
            owner = text.lstrip("@").strip()
            msg = await message.reply_text(f"🔍 Fetching repositories for <code>{owner}</code>...")
            repos = await DockerInspector.fetch_user_repos(owner)
            if not repos:
                await msg.edit_text("❌ No public repositories found or invalid URL. Please send full repo URL.")
                return

            session["owner"] = owner
            session["user_repos"] = repos
            buttons = []
            for r in repos[:10]: # Top 10 repos
                buttons.append([InlineKeyboardButton(f"📦 {r['name']}", callback_data=f"select_user_repo_{r['name']}")])
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")])
            await msg.edit_text("📦 <b>Available Repositories:</b>\nSelect a repository to deploy:", reply_markup=InlineKeyboardMarkup(buttons))

    elif step == "AWAIT_SERVICE_NAME":
        session["name"] = text

        # IF DOCKER MODE: NEVER ask for buildCommand/startCommand!
        if session.get("is_docker"):
            session["step"] = "AWAIT_ENV_VARS"
            await message.reply_text(
                f"✅ Service Name: <code>{text}</code>\n\n"
                "Enter Environment Variables in <code>KEY=value</code> format (one per line).\n"
                "Or click 'Skip Env Vars' to proceed.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_env_vars")]
                ])
            )
        else:
            session["step"] = "AWAIT_BUILD_COMMAND"
            await message.reply_text(
                "Please enter the Build Command:\n"
                "<i>Example: pip install -r requirements.txt</i>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Skip / None", callback_data="skip_build_cmd")]
                ])
            )

    elif step == "AWAIT_BUILD_COMMAND":
        session["buildCommand"] = text
        session["step"] = "AWAIT_START_COMMAND"
        await message.reply_text(
            "Please enter the Start Command:\n"
            "<i>Example: python -m bot</i>"
        )

    elif step == "AWAIT_START_COMMAND":
        session["startCommand"] = text
        session["step"] = "AWAIT_ENV_VARS"
        await message.reply_text(
            "Enter Environment Variables in <code>KEY=value</code> format (one per line).\n"
            "Or click 'Skip Env Vars' to proceed.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_env_vars")]
            ])
        )

    elif step == "AWAIT_ENV_VARS":
        parsed_vars = {}
        for line in text.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                parsed_vars[k.strip()] = v.strip()
        session["env_vars"].update(parsed_vars)
        session["step"] = "CONFIRMATION"
        DEPLOY_SESSIONS[user_id] = session
        await show_deployment_preview(client, message.chat.id, user_id)

@Client.on_callback_query(filters.regex("^select_user_repo_(.+)$") & auth_filter)
async def select_user_repo_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    repo_name = callback_query.matches[0].group(1).strip()
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    owner = session["owner"]
    session["repo_name"] = repo_name
    session["repo"] = f"https://github.com/{owner}/{repo_name}"
    await callback_query.message.edit_text(f"✅ Repository selected: <code>{owner}/{repo_name}</code>")
    await fetch_and_show_branches(client, callback_query.message.chat.id, user_id, session)

async def fetch_and_show_branches(client: Client, chat_id: int, user_id: int, session: Dict[str, Any]):
    owner = session["owner"]
    repo_name = session["repo_name"]
    session["step"] = "AWAIT_BRANCH_SELECT"

    msg = await client.send_message(chat_id, f"🌿 Fetching branches for <code>{owner}/{repo_name}</code>...")
    branches = await DockerInspector.fetch_repo_branches(owner, repo_name)
    session["fetched_branches"] = branches
    DEPLOY_SESSIONS[user_id] = session

    buttons = []
    row = []
    for idx, b in enumerate(branches[:12]):
        row.append(InlineKeyboardButton(f"🌿 {b}", callback_data=f"select_branch_{idx}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")])

    await msg.edit_text(
        f"🌿 <b>Available Branches for {owner}/{repo_name}:</b>\nSelect a branch to deploy:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("^select_branch_(\\d+)$") & auth_filter)
async def select_branch_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or "fetched_branches" not in session:
        return

    branch = session["fetched_branches"][idx]
    session["branch"] = branch
    await callback_query.message.edit_text(f"✅ Selected Branch: <code>{branch}</code>")
    await proceed_after_branch(client, callback_query.message.chat.id, user_id, session)

async def proceed_after_branch(client: Client, chat_id: int, user_id: int, session: Dict[str, Any]):
    owner = session["owner"]
    repo_name = session["repo_name"]
    branch = session.get("branch", "main")

    if session.get("is_docker"):
        status_msg = await client.send_message(chat_id, "🔍 Inspecting repository for Dockerfile...")
        detected = await DockerInspector.detect_dockerfiles(owner, repo_name, branch)

        if not detected:
            await status_msg.edit_text(
                "❌ <b>Dockerfile not found</b> in repository.\n\n"
                "You can generate a production Dockerfile or check the repo.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛠 Generate Dockerfile", callback_data="generate_dockerfile")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
                ])
            )
            return

        if len(detected) == 1:
            session["dockerfilePath"] = detected[0]
            session["dockerContext"] = "."
            await status_msg.edit_text(
                f"✅ Detected Dockerfile: <code>{detected[0]}</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Check Dockerfile", callback_data="check_dockerfile")],
                    [InlineKeyboardButton("➡️ Continue to Service Type", callback_data="proceed_service_type")]
                ])
            )
        else:
            buttons = [[InlineKeyboardButton(df, callback_data=f"select_df_{idx}")] for idx, df in enumerate(detected)]
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")])
            session["detected_dockerfiles"] = detected
            await status_msg.edit_text(
                "🐳 <b>Multiple Dockerfiles detected:</b>\nPlease select one:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        session["step"] = "SELECT_SERVICE_TYPE"
        await client.send_message(
            chat_id,
            "Select Service Type:",
            reply_markup=get_service_type_keyboard()
        )

@Client.on_callback_query(filters.regex("^select_df_(\\d+)$") & auth_filter)
async def select_dockerfile_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or "detected_dockerfiles" not in session:
        return
    df_path = session["detected_dockerfiles"][idx]
    session["dockerfilePath"] = df_path
    session["dockerContext"] = "."
    await callback_query.message.edit_text(
        f"✅ Selected Dockerfile: <code>{df_path}</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Check Dockerfile", callback_data="check_dockerfile")],
            [InlineKeyboardButton("➡️ Continue to Service Type", callback_data="proceed_service_type")]
        ])
    )

@Client.on_callback_query(filters.regex("^check_dockerfile$") & auth_filter)
async def check_dockerfile_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    df_path = session.get("dockerfilePath", "Dockerfile")
    content = await DockerInspector.fetch_repo_file(session["owner"], session["repo_name"], session.get("branch", "main"), df_path)

    if content is None:
        await callback_query.message.edit_text("❌ Failed to fetch Dockerfile content from GitHub.")
        return

    res = DockerInspector.validate_dockerfile(content)
    text = f"🔍 <b>Dockerfile Validation Result:</b>\n\n"
    if res.is_valid:
        text += "✅ <b>Status:</b> Valid Dockerfile syntax\n"
    else:
        text += "❌ <b>Status:</b> Invalid / Issues Found\n"

    if res.errors:
        text += "\n<b>Errors:</b>\n" + "\n".join([f"• {e}" for e in res.errors])
    if res.warnings:
        text += "\n<b>Warnings:</b>\n" + "\n".join([f"• {w}" for w in res.warnings])

    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Fix Dockerfile", callback_data="fix_dockerfile")],
            [InlineKeyboardButton("➡️ Proceed to Service Type", callback_data="proceed_service_type")]
        ])
    )

@Client.on_callback_query(filters.regex("^fix_dockerfile$") & auth_filter)
async def fix_dockerfile_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    df_path = session.get("dockerfilePath", "Dockerfile")
    content = await DockerInspector.fetch_repo_file(session["owner"], session["repo_name"], session.get("branch", "main"), df_path) or ""
    fixed_content, diff_text = DockerInspector.fix_dockerfile(content, project_type="python")

    await callback_query.message.edit_text(
        f"🛠 <b>Dockerfile Auto-Fix Preview (Diff):</b>\n\n"
        f"<code>{diff_text}</code>\n\n"
        f"<i>Preserving project logic while resolving Docker constraints.</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Proceed with Fixed Setup", callback_data="proceed_service_type")]
        ])
    )

@Client.on_callback_query(filters.regex("^generate_dockerfile$") & auth_filter)
async def generate_dockerfile_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    template = DockerInspector.generate_dockerfile_template("python")
    session["dockerfilePath"] = "./Dockerfile"
    session["dockerContext"] = "."

    await callback_query.message.edit_text(
        f"🛠 <b>Generated Production Dockerfile:</b>\n\n"
        f"<code>{template}</code>\n\n"
        f"Render will use this Dockerfile template for deployment.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Continue to Service Type", callback_data="proceed_service_type")]
        ])
    )

@Client.on_callback_query(filters.regex("^proceed_service_type$") & auth_filter)
async def proceed_service_type_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return
    session["step"] = "SELECT_SERVICE_TYPE"
    await callback_query.message.edit_text(
        "Select Service Type:",
        reply_markup=get_service_type_keyboard()
    )

@Client.on_callback_query(filters.regex("^(skip_build_cmd|skip_env_vars)$") & auth_filter)
async def skip_step_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    if action == "skip_build_cmd":
        session["buildCommand"] = ""
        session["step"] = "AWAIT_START_COMMAND"
        await callback_query.message.edit_text(
            "Please enter the Start Command:\n<i>Example: python -m bot</i>"
        )
    elif action == "skip_env_vars":
        session["step"] = "CONFIRMATION"
        await show_deployment_preview(client, callback_query.message.chat.id, user_id)

async def show_deployment_preview(client: Client, chat_id: int, user_id: int):
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return

    preview_text = format_deployment_preview(session)
    await client.send_message(
        chat_id,
        preview_text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 Confirm & Deploy", callback_data="confirm_deploy"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")
            ]
        ])
    )

@Client.on_callback_query(filters.regex("^confirm_deploy$") & auth_filter)
async def confirm_deploy_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Deployment session expired.")
        return

    api_key = await db.get_user_render_key(user_id)
    render = RenderAPI(api_key)

    msg = await callback_query.message.edit_text("⏳ <b>Creating service on Render...</b>")

    try:
        res = await render.create_service(session)
        srv = res.get("service", res)
        srv_id = srv.get("id")
        srv_name = srv.get("name")
        srv_url = srv.get("serviceDetails", {}).get("url", "")

        await db.save_deployment(
            user_id=user_id,
            service_id=srv_id,
            service_name=srv_name,
            repo_url=session["repo"],
            branch=session.get("branch", "main"),
            service_type=session.get("type", "web_service"),
            is_docker=session.get("is_docker", False),
            status="created",
            service_url=srv_url
        )

        await db.log_action(user_id, "DEPLOY_SERVICE", {"service_id": srv_id, "name": srv_name})
        DEPLOY_SESSIONS.pop(user_id, None)

        text = (
            f"✅ <b>Deployment Triggered Successfully!</b>\n\n"
            f"<b>Service:</b> {srv_name}\n"
            f"<b>ID:</b> <code>{srv_id}</code>\n"
        )
        if srv_url:
            text += f"<b>URL:</b> {srv_url}\n"

        await msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📜 View Logs", callback_data=f"logs_{srv_id}"),
                    InlineKeyboardButton("📊 Status", callback_data=f"status_{srv_id}")
                ],
                [InlineKeyboardButton("📂 All Projects", callback_data="list_projects")]
            ])
        )
    except RenderAPIError as e:
        await msg.edit_text(f"❌ <b>Deployment Failed:</b> {e.message}")
    except Exception as e:
        logger.error(f"Error creating service: {e}")
        await msg.edit_text(f"❌ <b>Error:</b> {str(e)}")

@Client.on_callback_query(filters.regex("^cancel_deploy$") & auth_filter)
async def cancel_deploy_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    DEPLOY_SESSIONS.pop(user_id, None)
    await callback_query.message.edit_text("❌ Deployment canceled.")
