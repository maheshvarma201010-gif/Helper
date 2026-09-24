import logging
import re
from typing import Dict, Any, List
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.github_check import check_user_github_connection
from bot.utils.docker_inspector import DockerInspector
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.formatter import format_deployment_preview, sanitize_service_name, get_status_badge
from bot.utils.env_converter_util import parse_env_input

logger = logging.getLogger(__name__)

DEPLOY_SESSIONS: Dict[int, Dict[str, Any]] = {}

ALL_COMMANDS = [
    "start", "help", "deploy", "create_repo", "zip", "repo_upload", "repos",
    "projects", "status", "logs", "restart", "redeploy", "redeploy_all",
    "stop", "delete", "env", "env_converter", "delete_branches", "settings"
]

# --- Keyboards ---

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])

def get_runtime_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🐳 Docker", callback_data="select_runtime_docker"),
            InlineKeyboardButton("🐍 Python", callback_data="select_runtime_python")
        ],
        [
            InlineKeyboardButton("🟢 Node.js", callback_data="select_runtime_node"),
            InlineKeyboardButton("🐹 Go", callback_data="select_runtime_go")
        ],
        [
            InlineKeyboardButton("💎 Ruby", callback_data="select_runtime_ruby"),
            InlineKeyboardButton("🦀 Rust", callback_data="select_runtime_rust")
        ],
        [
            InlineKeyboardButton("💧 Elixir", callback_data="select_runtime_elixir"),
            InlineKeyboardButton("📄 Static Site", callback_data="select_runtime_static")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])

def get_region_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇸 Oregon (us-west)", callback_data="select_region_oregon"),
            InlineKeyboardButton("🇩🇪 Frankfurt (eu-central)", callback_data="select_region_frankfurt")
        ],
        [
            InlineKeyboardButton("🇸🇬 Singapore (ap-southeast)", callback_data="select_region_singapore"),
            InlineKeyboardButton("🇺🇸 Ohio (us-east)", callback_data="select_region_ohio")
        ],
        [
            InlineKeyboardButton("🇺🇸 Virginia (us-east)", callback_data="select_region_virginia")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])

def get_plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆓 Free ($0/mo)", callback_data="select_plan_free"),
            InlineKeyboardButton("🚀 Starter ($7/mo)", callback_data="select_plan_starter")
        ],
        [
            InlineKeyboardButton("⚡ Standard ($25/mo)", callback_data="select_plan_standard"),
            InlineKeyboardButton("💼 Pro ($85/mo)", callback_data="select_plan_pro")
        ],
        [
            InlineKeyboardButton("🔥 Pro Plus ($175/mo)", callback_data="select_plan_pro_plus"),
            InlineKeyboardButton("👑 Extra Pro ($225/mo)", callback_data="select_plan_extra_pro")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])

# --- Entry Commands ---

@Client.on_message(filters.command("deploy") & auth_filter)
async def deploy_command(client: Client, message: Message):
    user_id = message.from_user.id

    connected, error_msg, keyboard = await check_user_github_connection(user_id)
    if not connected:
        await message.reply_text(error_msg, reply_markup=keyboard)
        return

    DEPLOY_SESSIONS[user_id] = {
        "step": "AWAIT_SERVICE_NAME",
        "env_vars": {},
        "type": "web_service"
    }

    await message.reply_text(
        "🚀 <b>New Render Deployment</b>\n\n"
        "<b>Step 1/7: Service Name</b>\n"
        "Please enter a unique Service Name for your deployment:\n"
        "<i>Example: my-web-app</i>",
        reply_markup=get_cancel_keyboard()
    )

@Client.on_callback_query(filters.regex("^start_deploy$") & auth_filter)
async def start_deploy_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    connected, error_msg, keyboard = await check_user_github_connection(user_id)
    if not connected:
        await callback_query.message.edit_text(error_msg, reply_markup=keyboard)
        return

    DEPLOY_SESSIONS[user_id] = {
        "step": "AWAIT_SERVICE_NAME",
        "env_vars": {},
        "type": "web_service"
    }
    await callback_query.message.edit_text(
        "🚀 <b>New Render Deployment</b>\n\n"
        "<b>Step 1/7: Service Name</b>\n"
        "Please enter a unique Service Name for your deployment:\n"
        "<i>Example: my-web-app</i>",
        reply_markup=get_cancel_keyboard()
    )

# --- Step Helper Functions ---

async def prompt_step_2_repository(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    session["step"] = "AWAIT_REPO"
    DEPLOY_SESSIONS[user_id] = session

    text = (
        f"✅ <b>Service Name:</b> <code>{session['name']}</code>\n\n"
        "<b>Step 2/7: Repository</b>\n"
        "Please send the GitHub repository URL or Owner/Repo:\n"
        "<i>Examples: https://github.com/owner/repository OR owner/repository</i>"
    )
    kb = get_cancel_keyboard()
    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)

async def prompt_step_3_runtime(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    session["step"] = "AWAIT_RUNTIME"
    DEPLOY_SESSIONS[user_id] = session

    text = (
        f"✅ <b>Repository:</b> <code>{session['owner']}/{session['repo_name']}</code>\n\n"
        "<b>Step 3/7: Language / Runtime</b>\n"
        "Select the runtime for your application:"
    )
    kb = get_runtime_keyboard()
    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)

async def prompt_step_4_branch(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None, page: int = 0):
    owner = session["owner"]
    repo_name = session["repo_name"]
    gh_token = await db.get_user_github_token(user_id)

    branches = session.get("fetched_branches")
    if branches is None:
        if message_to_edit:
            await message_to_edit.edit_text(f"🌿 Fetching branches for <code>{owner}/{repo_name}</code>...")
        else:
            msg = await client.send_message(chat_id, f"🌿 Fetching branches for <code>{owner}/{repo_name}</code>...")
            message_to_edit = msg

        branches = await DockerInspector.fetch_repo_branches(owner, repo_name, github_token=gh_token)
        session["fetched_branches"] = branches
        DEPLOY_SESSIONS[user_id] = session

    # Step 4 Rule: If 1 branch, automatically select it without asking user
    if len(branches) == 1:
        selected_b = branches[0]
        session["branch"] = selected_b
        DEPLOY_SESSIONS[user_id] = session
        info_text = f"✅ <b>Branch:</b> Single branch detected: <code>{selected_b}</code> (auto-selected)."
        if message_to_edit:
            await message_to_edit.edit_text(info_text)
        else:
            await client.send_message(chat_id, info_text)
        await prompt_step_5_region(client, chat_id, user_id, session)
        return

    if not branches:
        session["branch"] = "main"
        DEPLOY_SESSIONS[user_id] = session
        info_text = "⚠️ Could not fetch branches. Defaulting to <code>main</code> branch."
        if message_to_edit:
            await message_to_edit.edit_text(info_text)
        else:
            await client.send_message(chat_id, info_text)
        await prompt_step_5_region(client, chat_id, user_id, session)
        return

    session["step"] = "AWAIT_BRANCH"
    DEPLOY_SESSIONS[user_id] = session

    PAGE_SIZE = 8
    total_branches = len(branches)
    total_pages = (total_branches + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_branches)
    page_branches = branches[start_idx:end_idx]

    buttons = []
    row = []
    for idx, b in enumerate(page_branches):
        global_idx = start_idx + idx
        row.append(InlineKeyboardButton(f"🌿 {b}", callback_data=f"select_branch_idx_{global_idx}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"select_branch_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"Page {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"select_branch_page_{page + 1}"))

    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")])

    text = f"<b>Step 4/7: Branch</b>\nAvailable branches for <code>{owner}/{repo_name}</code> ({total_branches} Total):\nSelect a branch:"

    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))

async def prompt_step_5_region(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    session["step"] = "AWAIT_REGION"
    DEPLOY_SESSIONS[user_id] = session

    text = (
        f"✅ <b>Branch Selected:</b> <code>{session.get('branch', 'main')}</code>\n\n"
        "<b>Step 5/7: Region</b>\n"
        "Select the Render deployment region:"
    )
    kb = get_region_keyboard()
    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)

async def prompt_step_6_plan(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    session["step"] = "AWAIT_PLAN"
    DEPLOY_SESSIONS[user_id] = session

    text = (
        f"✅ <b>Region Selected:</b> <code>{session.get('region', 'oregon')}</code>\n\n"
        "<b>Step 6/7: Compute Plan</b>\n"
        "Select your compute plan / instance type (all options shown below):"
    )
    kb = get_plan_keyboard()
    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)

async def prompt_step_7_env_vars(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    session["step"] = "AWAIT_ENV_VARS"
    DEPLOY_SESSIONS[user_id] = session

    text = (
        f"✅ <b>Plan Selected:</b> <code>{session.get('plan', 'free').upper()}</code>\n\n"
        "<b>Step 7/7: Environment Variables</b>\n"
        "Enter Environment Variables in <code>KEY=value</code> format (one per line).\n"
        "Or click 'Skip Env Vars' to proceed."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_env_vars")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
    ])
    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)

# --- Callbacks ---

@Client.on_callback_query(filters.regex("^select_runtime_(docker|python|node|go|ruby|rust|elixir|static)$") & auth_filter)
async def select_runtime_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    runtime = callback_query.matches[0].group(1)
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_RUNTIME":
        await callback_query.answer("Invalid or expired step.", show_alert=True)
        return

    session["env"] = runtime
    if runtime == "docker":
        session["is_docker"] = True
        session["dockerfilePath"] = "./Dockerfile"
        session["dockerContext"] = "."
        await callback_query.message.edit_text(f"✅ Runtime: <code>Docker</code>")
        await prompt_step_4_branch(client, callback_query.message.chat.id, user_id, session)
    elif runtime == "static":
        session["is_docker"] = False
        session["type"] = "static_site"
        session["step"] = "AWAIT_BUILD_COMMAND"
        DEPLOY_SESSIONS[user_id] = session
        await callback_query.message.edit_text(
            "✅ Runtime: <code>Static Site</code>\n\n"
            "Please enter the Build Command (e.g. <code>npm run build</code>) or click Skip:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip / None", callback_data="skip_build_cmd")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
            ])
        )
    else:
        session["is_docker"] = False
        session["step"] = "AWAIT_BUILD_COMMAND"
        DEPLOY_SESSIONS[user_id] = session
        await callback_query.message.edit_text(
            f"✅ Runtime: <code>{runtime.title()}</code>\n\n"
            f"Please enter the Build Command (e.g. <code>pip install -r requirements.txt</code> or <code>npm install</code>) or click Skip:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip / None", callback_data="skip_build_cmd")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
            ])
        )

@Client.on_callback_query(filters.regex("^skip_build_cmd$") & auth_filter)
async def skip_build_cmd_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_BUILD_COMMAND":
        await callback_query.answer("Invalid or expired step.", show_alert=True)
        return

    session["buildCommand"] = ""
    session["step"] = "AWAIT_START_COMMAND"
    DEPLOY_SESSIONS[user_id] = session
    await callback_query.message.edit_text(
        "Please enter the Start Command (e.g. <code>python -m bot</code> or <code>npm start</code>) or click Skip:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Skip / None", callback_data="skip_start_cmd")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
        ])
    )

@Client.on_callback_query(filters.regex("^skip_start_cmd$") & auth_filter)
async def skip_start_cmd_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_START_COMMAND":
        await callback_query.answer("Invalid or expired step.", show_alert=True)
        return

    session["startCommand"] = ""
    await prompt_step_4_branch(client, callback_query.message.chat.id, user_id, session, message_to_edit=callback_query.message)

@Client.on_callback_query(filters.regex("^select_branch_page_(\\d+)$") & auth_filter)
async def branch_page_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        return
    await prompt_step_4_branch(client, callback_query.message.chat.id, user_id, session, message_to_edit=callback_query.message, page=page)

@Client.on_callback_query(filters.regex("^select_branch_idx_(\\d+)$") & auth_filter)
async def select_branch_idx_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_BRANCH":
        await callback_query.answer("Session expired or invalid step.", show_alert=True)
        return

    branches = session.get("fetched_branches", [])
    if idx < 0 or idx >= len(branches):
        await callback_query.answer("Invalid branch selection.", show_alert=True)
        return

    branch = branches[idx]
    session["branch"] = branch
    await callback_query.message.edit_text(f"✅ Selected Branch: <code>{branch}</code>")
    await prompt_step_5_region(client, callback_query.message.chat.id, user_id, session)

@Client.on_callback_query(filters.regex("^select_region_(oregon|frankfurt|singapore|ohio|virginia)$") & auth_filter)
async def select_region_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    region = callback_query.matches[0].group(1)
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_REGION":
        await callback_query.answer("Session expired or invalid step.", show_alert=True)
        return

    session["region"] = region
    await callback_query.message.edit_text(f"✅ Region: <code>{region}</code>")
    await prompt_step_6_plan(client, callback_query.message.chat.id, user_id, session)

@Client.on_callback_query(filters.regex("^select_plan_(free|starter|standard|pro|pro_plus|extra_pro)$") & auth_filter)
async def select_plan_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    plan_choice = callback_query.matches[0].group(1)
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_PLAN":
        await callback_query.answer("Session expired or invalid step.", show_alert=True)
        return

    session["plan"] = plan_choice
    session["instance_type"] = plan_choice
    await callback_query.message.edit_text(f"✅ Compute Plan: <code>{plan_choice.upper()}</code>")
    await prompt_step_7_env_vars(client, callback_query.message.chat.id, user_id, session)

@Client.on_callback_query(filters.regex("^skip_env_vars$") & auth_filter)
async def skip_env_vars_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_ENV_VARS":
        await callback_query.answer("Session expired or invalid step.", show_alert=True)
        return

    session["step"] = "CONFIRMATION"
    DEPLOY_SESSIONS[user_id] = session
    await show_deployment_preview(client, callback_query.message.chat.id, user_id)

@Client.on_callback_query(filters.regex("^cancel_deploy$") & auth_filter)
async def cancel_deploy_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    DEPLOY_SESSIONS.pop(user_id, None)
    await callback_query.message.edit_text("❌ Deployment canceled.")

# --- Text Handlers ---

@Client.on_message(filters.text & ~filters.command(ALL_COMMANDS) & auth_filter)
async def wizard_text_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = DEPLOY_SESSIONS.get(user_id)
    if not session:
        message.continue_propagation()
        return

    step = session.get("step")
    text = message.text.strip()
    gh_token = await db.get_user_github_token(user_id)

    # Step 1 Validation
    if step == "AWAIT_SERVICE_NAME":
        if not text or len(text) < 2:
            await message.reply_text(
                "❌ <b>Invalid Service Name</b>\n"
                "Please enter a valid service name containing at least 2 characters (alphanumeric and hyphens).",
                reply_markup=get_cancel_keyboard()
            )
            return

        sanitized_name = sanitize_service_name(text)
        if not sanitized_name:
            await message.reply_text(
                "❌ <b>Invalid Service Name Format</b>\n"
                "Service name must contain alphanumeric characters or hyphens.",
                reply_markup=get_cancel_keyboard()
            )
            return

        session["name"] = sanitized_name
        await prompt_step_2_repository(client, message.chat.id, user_id, session)

    # Step 2 Validation
    elif step == "AWAIT_REPO":
        parsed = DockerInspector.parse_github_url(text)
        if not parsed:
            await message.reply_text(
                "❌ <b>Invalid Repository URL or Format</b>\n"
                "Please send a valid GitHub URL or Owner/Repo pair.\n"
                "<i>Example: https://github.com/owner/repo OR owner/repo</i>",
                reply_markup=get_cancel_keyboard()
            )
            return

        owner, repo_name = parsed
        session["repo"] = f"https://github.com/{owner}/{repo_name}"
        session["owner"] = owner
        session["repo_name"] = repo_name

        await prompt_step_3_runtime(client, message.chat.id, user_id, session)

    elif step == "AWAIT_BUILD_COMMAND":
        session["buildCommand"] = text
        session["step"] = "AWAIT_START_COMMAND"
        DEPLOY_SESSIONS[user_id] = session
        await message.reply_text(
            "Please enter the Start Command (e.g. <code>python -m bot</code> or <code>npm start</code>) or click Skip:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip / None", callback_data="skip_start_cmd")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
            ])
        )

    elif step == "AWAIT_START_COMMAND":
        session["startCommand"] = text
        await prompt_step_4_branch(client, message.chat.id, user_id, session)

    # Step 7 Validation
    elif step == "AWAIT_ENV_VARS":
        parsed_vars = parse_env_input(text)
        if not parsed_vars and "=" in text:
            await message.reply_text(
                "⚠️ <b>Environment Variable Format Error</b>\n"
                "Please format variables as <code>KEY=value</code> (one per line).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_env_vars")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_deploy")]
                ])
            )
            return

        session["env_vars"].update(parsed_vars)
        session["step"] = "CONFIRMATION"
        DEPLOY_SESSIONS[user_id] = session
        await show_deployment_preview(client, message.chat.id, user_id)

# --- Step 8 & Step 9: Confirmation & Trigger Deployment ---

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
    if not api_key:
        await callback_query.message.edit_text(
            "🔑 <b>Render API Key Required</b>\n\n"
            "Please configure your Render API key in /settings before deploying.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]])
        )
        return

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
            f"<b>Service Name:</b> {srv_name}\n"
            f"<b>Service ID:</b> <code>{srv_id}</code>\n"
            f"<b>Status:</b> {get_status_badge('created')}\n"
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
        err_msg = f"❌ <b>Deployment Failed (API Error {e.status}):</b> {e.message}"
        if "payment" in e.message.lower() or "card" in e.message.lower() or "billing" in e.message.lower():
            err_msg += "\n\n💡 <b>Tip:</b> Render requires a valid payment method on file to spin up non-free instances or extra resources. Visit https://dashboard.render.com/billing to update billing."
        await msg.edit_text(err_msg)
    except Exception as e:
        logger.error(f"Error creating service: {e}")
        await msg.edit_text(f"❌ <b>Error:</b> {str(e)}")
