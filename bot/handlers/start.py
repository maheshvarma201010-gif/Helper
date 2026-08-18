from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from bot.config import Config
from bot.utils.security import auth_filter
from bot.utils.github_check import check_user_github_connection, GITHUB_AUTH_URL

START_TEXT = (
    "🚀 <b>Welcome to Render Deployer Bot</b>\n\n"
    "Deploy, manage, and monitor your web services, background workers, cron jobs, "
    "and Docker applications on Render directly from Telegram.\n\n"
    "<b>Features:</b>\n"
    "• 🐳 Standard & Dockerfile Deployments\n"
    "• 📦 /repos - View & select all your public & private GitHub repos\n"
    "• 🔍 Automatic Dockerfile detection, inspection & auto-fix\n"
    "• ⚙️ Environment variables manager & Live Branch/Repo Switcher\n"
    "• 📊 Real-time logs, status monitoring, and service restart\n\n"
    "Select an option below to get started:"
)

HELP_TEXT = (
    "📖 <b>Render Deployer Bot - Command Documentation</b>\n\n"
    "<b>Commands:</b>\n"
    "• /start - Welcome menu and available actions\n"
    "• /create_repo - Import or create a repository and deploy\n"
    "• /deploy - Start a new application deployment\n"
    "• /repos - View & deploy public and private GitHub repositories\n"
    "• /projects - List connected Render services\n"
    "• /status - View real-time status of services\n"
    "• /logs - View recent build/runtime logs\n"
    "• /restart - Restart a service\n"
    "• /redeploy - Trigger a new deployment\n"
    "• /stop - Suspend a service\n"
    "• /delete - Safely delete a service\n"
    "• /env - View and manage environment variables\n"
    "• /settings - Configure Render API token and GitHub PAT\n"
    "• /help - Show this help menu"
)

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🛠 Create/Import Repo", callback_data="open_create_repo"),
            InlineKeyboardButton("🚀 Deploy", callback_data="start_deploy")
        ],
        [
            InlineKeyboardButton("📦 My Repos", callback_data="list_repos_0"),
            InlineKeyboardButton("📂 Projects", callback_data="list_projects")
        ],
        [
            InlineKeyboardButton("⚙️ Env Vars", callback_data="manage_env"),
            InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")
        ],
        [
            InlineKeyboardButton("🔗 Connect GitHub", url=GITHUB_AUTH_URL),
            InlineKeyboardButton("📖 Help", callback_data="show_help")
        ]
    ]

    # Only include WebAppInfo button if HTTPS is configured, preventing Telegram WebApp URL validation errors
    if Config.PORT == 443:
        buttons.insert(1, [InlineKeyboardButton("📱 Render Mini App", web_app=WebAppInfo(url=f"https://localhost/miniapp"))])

    return InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command("start") & auth_filter)
async def start_command(client: Client, message: Message):
    await message.reply_text(
        text=START_TEXT,
        reply_markup=get_main_menu_keyboard(),
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("help") & auth_filter)
async def help_command(client: Client, message: Message):
    await message.reply_text(
        text=HELP_TEXT,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
    )

@Client.on_callback_query(filters.regex("^open_create_repo$") & auth_filter)
async def open_create_repo_callback(client: Client, callback_query: CallbackQuery):
    from bot.handlers.create_repo import get_create_repo_choice_keyboard, CREATE_REPO_SESSIONS
    user_id = callback_query.from_user.id
    CREATE_REPO_SESSIONS[user_id] = {"step": "CHOICE"}
    await callback_query.message.edit_text(
        "🛠 <b>Repository & Deployment Wizard (/create_repo)</b>\n\n"
        "Would you like to <b>Import</b> an existing repository or <b>Create</b> a brand new repository?",
        reply_markup=get_create_repo_choice_keyboard()
    )

@Client.on_callback_query(filters.regex("^main_menu$") & auth_filter)
async def main_menu_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        text=START_TEXT,
        reply_markup=get_main_menu_keyboard(),
        disable_web_page_preview=True
    )

@Client.on_callback_query(filters.regex("^show_help$") & auth_filter)
async def help_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        text=HELP_TEXT,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
    )

@Client.on_callback_query(filters.regex("^verify_github_conn$") & auth_filter)
async def verify_github_callback(client: Client, callback_query: CallbackQuery):
    connected, error_msg, keyboard = await check_user_github_connection(callback_query.from_user.id)
    if connected:
        await callback_query.answer("✅ Render API & GitHub authorization verified!", show_alert=True)
        await callback_query.message.edit_text(
            text=f"✅ <b>Connected & Authorized</b>\n\n{START_TEXT}",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await callback_query.answer("⚠️ Connection check failed.", show_alert=True)
        await callback_query.message.edit_text(
            text=error_msg,
            reply_markup=keyboard
        )
