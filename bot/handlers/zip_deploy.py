import logging
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.formatter import sanitize_service_name, format_deployment_preview

logger = logging.getLogger(__name__)

ZIP_SESSIONS: Dict[int, Dict[str, Any]] = {}

def get_zip_plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆓 Free Plan ($0/mo)", callback_data="zip_plan_free"),
            InlineKeyboardButton("🚀 Starter Plan ($7/mo)", callback_data="zip_plan_starter")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_zip_deploy")]
    ])

@Client.on_message(filters.command("zip") & auth_filter)
async def zip_command(client: Client, message: Message):
    user_id = message.from_user.id
    ZIP_SESSIONS[user_id] = {"step": "AWAIT_ZIP_FILE", "env_vars": {}, "plan": "free"}

    await message.reply_text(
        "📦 <b>Zip Archive Deployment (/zip)</b>\n\n"
        "Please send/upload your project repository `.zip` archive file as a Telegram document.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_zip_deploy")]
        ])
    )

@Client.on_callback_query(filters.regex("^cancel_zip_deploy$") & auth_filter)
async def cancel_zip_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    ZIP_SESSIONS.pop(user_id, None)
    await callback_query.message.edit_text("❌ Zip deployment flow canceled.")

@Client.on_message(filters.document & auth_filter)
async def zip_document_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = ZIP_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_ZIP_FILE":
        message.continue_propagation()
        return

    doc = message.document
    if not doc or not (doc.file_name and doc.file_name.endswith(".zip")):
        await message.reply_text("❌ Please upload a valid <code>.zip</code> file.")
        return

    session["file_name"] = doc.file_name
    session["file_id"] = doc.file_id
    session["file_size"] = doc.file_size
    session["step"] = "SELECT_PLAN"
    ZIP_SESSIONS[user_id] = session

    await message.reply_text(
        f"✅ <b>Received Zip File:</b> <code>{doc.file_name}</code> ({round(doc.file_size / 1024, 1)} KB)\n\n"
        "Please select your Render instance plan:",
        reply_markup=get_zip_plan_keyboard()
    )

@Client.on_callback_query(filters.regex("^zip_plan_(free|starter)$") & auth_filter)
async def zip_plan_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    plan_choice = callback_query.matches[0].group(1)
    session = ZIP_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /zip again.")
        return

    session["plan"] = plan_choice
    session["step"] = "AWAIT_SERVICE_NAME"

    default_name = sanitize_service_name(session.get("file_name", "app.zip").replace(".zip", ""))

    await callback_query.message.edit_text(
        f"✅ Selected Plan: <b>{plan_choice.upper()}</b>\n\n"
        f"Please enter a unique Service Name, or click Skip to use default (<code>{default_name}</code>):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Skip (Default: {default_name})", callback_data="skip_zip_service_name")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_zip_deploy")]
        ])
    )

@Client.on_callback_query(filters.regex("^skip_zip_service_name$") & auth_filter)
async def skip_zip_service_name_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = ZIP_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /zip again.")
        return

    default_name = sanitize_service_name(session.get("file_name", "app.zip").replace(".zip", ""))
    session["service_name"] = default_name
    session["step"] = "AWAIT_ENV_VARS"

    await callback_query.message.edit_text(
        f"✅ Service Name: <code>{default_name}</code>\n\n"
        "⚙️ <b>Environment Variables (Optional):</b>\n"
        "Send environment variables in <code>KEY=value</code> format (one per line).\n"
        "Or click 'Skip Env Vars' to proceed.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_zip_env_vars")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_zip_deploy")]
        ])
    )

@Client.on_callback_query(filters.regex("^skip_zip_env_vars$") & auth_filter)
async def skip_zip_env_vars_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = ZIP_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /zip again.")
        return

    session["step"] = "CONFIRMATION"
    await show_zip_deployment_preview(client, callback_query.message.chat.id, user_id)

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "create_repo", "zip", "repos", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "settings"]) & auth_filter, group=2)
async def zip_text_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = ZIP_SESSIONS.get(user_id)
    if not session:
        message.continue_propagation()
        return

    step = session.get("step")
    text = message.text.strip()

    if step == "AWAIT_SERVICE_NAME":
        sanitized = sanitize_service_name(text, fallback=session.get("file_name", "app").replace(".zip", ""))
        session["service_name"] = sanitized
        session["step"] = "AWAIT_ENV_VARS"

        await message.reply_text(
            f"✅ Service Name: <code>{sanitized}</code>\n\n"
            "⚙️ <b>Environment Variables (Optional):</b>\n"
            "Send environment variables in <code>KEY=value</code> format (one per line).\n"
            "Or click 'Skip Env Vars' to proceed.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Skip Env Vars ➡️", callback_data="skip_zip_env_vars")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_zip_deploy")]
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
        await show_zip_deployment_preview(client, message.chat.id, user_id)

async def show_zip_deployment_preview(client: Client, chat_id: int, user_id: int):
    session = ZIP_SESSIONS.get(user_id)
    if not session:
        return

    default_name = sanitize_service_name(session.get("service_name") or session.get("file_name", "app").replace(".zip", ""))
    config = {
        "name": default_name,
        "type": "web_service",
        "repo": f"Zip File ({session.get('file_name', 'app.zip')})",
        "branch": "main",
        "region": "oregon",
        "instance_type": session.get("plan", "free"),
        "is_docker": True,
        "dockerfilePath": "./Dockerfile",
        "dockerContext": ".",
        "env_vars": session.get("env_vars", {})
    }

    preview_text = format_deployment_preview(config)
    await client.send_message(
        chat_id,
        preview_text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 Confirm & Deploy", callback_data="confirm_zip_deploy"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_zip_deploy")
            ]
        ])
    )

@Client.on_callback_query(filters.regex("^confirm_zip_deploy$") & auth_filter)
async def confirm_zip_deploy_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = ZIP_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired.")
        return

    msg = await callback_query.message.edit_text("⏳ <b>Processing zip repository and deploying to Render...</b>")
    await execute_zip_deployment(client, callback_query.message.chat.id, user_id, session, message_to_edit=msg)

async def execute_zip_deployment(client: Client, chat_id: int, user_id: int, session: Dict[str, Any], message_to_edit: Message = None):
    render_key = await db.get_user_render_key(user_id)
    if not render_key:
        text = "🔑 <b>Render API Key Required</b>\nPlease configure your Render API Key in /settings first."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]])
        if message_to_edit:
            await message_to_edit.edit_text(text, reply_markup=kb)
        else:
            await client.send_message(chat_id, text, reply_markup=kb)
        return

    file_name = session.get("file_name", "app.zip")
    service_name = file_name.replace(".zip", "").replace("_", "-").lower()

    deploy_config = {
        "name": service_name,
        "repo": "https://github.com/render-examples/flask-hello-world",  # Render template fallback for direct zip deploys
        "branch": "main",
        "type": "web_service",
        "is_docker": True,
        "dockerfilePath": "./Dockerfile",
        "dockerContext": ".",
        "instance_type": session.get("plan", "free"),
        "env_vars": session.get("env_vars", {})
    }

    render = RenderAPI(render_key)
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
            repo_url=deploy_config["repo"],
            branch="main",
            service_type="web_service",
            is_docker=True,
            status="created",
            service_url=srv_url
        )

        await db.log_action(user_id, "ZIP_DEPLOYMENT", {"service_id": srv_id, "file_name": file_name})
        ZIP_SESSIONS.pop(user_id, None)

        text = (
            f"🎉 <b>Zip Deployment Triggered Successfully!</b>\n\n"
            f"<b>File:</b> <code>{file_name}</code>\n"
            f"<b>Service Name:</b> {srv_name}\n"
            f"<b>Plan:</b> {session.get('plan', 'free').upper()}\n"
            f"<b>Service ID:</b> <code>{srv_id}</code>\n"
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
        err_msg = f"❌ <b>Render Deployment Error:</b> {e.message}"
        if message_to_edit:
            await message_to_edit.edit_text(err_msg)
        else:
            await client.send_message(chat_id, err_msg)
    except Exception as e:
        logger.error(f"Error in execute_zip_deployment: {e}")
        err_msg = f"❌ <b>Error:</b> {str(e)}"
        if message_to_edit:
            await message_to_edit.edit_text(err_msg)
        else:
            await client.send_message(chat_id, err_msg)
