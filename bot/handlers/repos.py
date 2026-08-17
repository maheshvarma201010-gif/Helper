import logging
from typing import Dict, Any, List
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.github_check import check_user_github_connection
from bot.utils.docker_inspector import DockerInspector
from bot.handlers.deploy import DEPLOY_SESSIONS, fetch_and_show_branches

logger = logging.getLogger(__name__)

# Memory cache for user repos per session: {user_id: [repos_list]}
USER_REPOS_CACHE: Dict[int, List[Dict[str, Any]]] = {}

@Client.on_message(filters.command("repos") & auth_filter)
async def repos_command(client: Client, message: Message):
    await show_user_repos(client, message.chat.id, message.from_user.id, page=0)

@Client.on_callback_query(filters.regex("^list_repos_(\\d+)$") & auth_filter)
async def list_repos_callback(client: Client, callback_query: CallbackQuery):
    page = int(callback_query.matches[0].group(1))
    await show_user_repos(client, callback_query.message.chat.id, callback_query.from_user.id, page=page, message_to_edit=callback_query.message)

async def show_user_repos(client: Client, chat_id: int, user_id: int, page: int = 0, message_to_edit: Message = None):
    gh_token = await db.get_user_github_token(user_id)

    if not gh_token:
        text = (
            "🐙 <b>GitHub Token Required for /repos</b>\n\n"
            "To view and select all your public and private GitHub repositories, "
            "please connect your GitHub Personal Access Token (PAT) in /settings."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🐙 Connect GitHub Token", callback_data="update_gh_token")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]
        ])
        if message_to_edit:
            await message_to_edit.edit_text(text, reply_markup=kb)
        else:
            await client.send_message(chat_id, text, reply_markup=kb)
        return

    # Check cache or fetch
    repos = USER_REPOS_CACHE.get(user_id)
    if not repos:
        if message_to_edit:
            await message_to_edit.edit_text("🔍 Fetching all public & private GitHub repositories...")
        else:
            msg = await client.send_message(chat_id, "🔍 Fetching all public & private GitHub repositories...")
            message_to_edit = msg

        repos = await DockerInspector.fetch_user_repos("me", github_token=gh_token)
        if repos is None:
            await message_to_edit.edit_text(
                "❌ <b>GitHub Token Error</b>\nFailed to authenticate with GitHub. Please update your PAT in /settings.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Update Token", callback_data="update_gh_token")]])
            )
            return

        USER_REPOS_CACHE[user_id] = repos

    if not repos:
        await message_to_edit.edit_text(
            "📦 <b>No repositories found in your GitHub account.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
        )
        return

    PAGE_SIZE = 8
    total_repos = len(repos)
    total_pages = (total_repos + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_repos)
    page_repos = repos[start_idx:end_idx]

    buttons = []
    for r in page_repos:
        name = r.get("name")
        full_name = r.get("full_name") or name
        is_private = r.get("private", False)
        icon = "🔒" if is_private else "📦"
        buttons.append([InlineKeyboardButton(f"{icon} {full_name}", callback_data=f"deploy_repo_{name}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"list_repos_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"Page {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"list_repos_{page + 1}"))

    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔄 Refresh Repos", callback_data="refresh_repos"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])

    text = (
        f"📦 <b>Your GitHub Repositories ({total_repos} Total):</b>\n"
        f"Select a repository below to deploy on Render:"
    )

    await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^refresh_repos$") & auth_filter)
async def refresh_repos_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    USER_REPOS_CACHE.pop(user_id, None)
    await show_user_repos(client, callback_query.message.chat.id, user_id, page=0, message_to_edit=callback_query.message)

@Client.on_callback_query(filters.regex("^deploy_repo_(.+)$") & auth_filter)
async def deploy_repo_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    repo_name = callback_query.matches[0].group(1).strip()

    repos = USER_REPOS_CACHE.get(user_id) or []
    selected_repo = None
    for r in repos:
        if r.get("name") == repo_name:
            selected_repo = r
            break

    if not selected_repo:
        await callback_query.answer("Repository not found in cache. Refreshing...", show_alert=True)
        return

    full_name = selected_repo.get("full_name", repo_name)
    parts = full_name.split("/")
    owner = parts[0] if len(parts) == 2 else "user"
    repo_short = parts[1] if len(parts) == 2 else repo_name

    DEPLOY_SESSIONS[user_id] = {
        "step": "AWAIT_BRANCH_SELECT",
        "is_docker": True, # Default to Dockerfile mode for quick repo deploy
        "repo": selected_repo.get("html_url", f"https://github.com/{full_name}"),
        "owner": owner,
        "repo_name": repo_short,
        "env_vars": {}
    }

    await callback_query.message.edit_text(f"✅ Selected Repository: <code>{full_name}</code>")
    await fetch_and_show_branches(client, callback_query.message.chat.id, user_id, DEPLOY_SESSIONS[user_id])
