import logging
from typing import Dict, Any, List, Set
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.security import auth_filter
from bot.utils.docker_inspector import DockerInspector

logger = logging.getLogger(__name__)

DELETE_BRANCHES_SESSIONS: Dict[int, Dict[str, Any]] = {}

def build_delete_branches_keyboard(user_id: int) -> InlineKeyboardMarkup:
    session = DELETE_BRANCHES_SESSIONS.get(user_id, {})
    branches = session.get("branches", [])
    selected: Set[str] = session.get("selected", set())
    page = session.get("page", 0)

    PAGE_SIZE = 8
    total_branches = len(branches)
    total_pages = max(1, (total_branches + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    session["page"] = page

    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_branches)
    page_branches = branches[start_idx:end_idx]

    buttons = []
    for idx, b in enumerate(page_branches):
        global_idx = start_idx + idx
        icon = "☑️" if b in selected else "🔲"
        buttons.append([InlineKeyboardButton(f"{icon} {b}", callback_data=f"del_br_item_{global_idx}")])

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"del_br_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"Page {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"del_br_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    select_all_label = "❌ Deselect All" if len(selected) == total_branches and total_branches > 0 else "✅ Select All"
    buttons.append([
        InlineKeyboardButton(select_all_label, callback_data="del_br_toggle_all"),
        InlineKeyboardButton(f"🗑 Delete ({len(selected)})", callback_data="del_br_confirm")
    ])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_del_branches")])

    return InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command("delete_branches") & auth_filter)
async def delete_branches_command(client: Client, message: Message):
    user_id = message.from_user.id
    gh_token = await db.get_user_github_token(user_id)

    if not gh_token:
        await message.reply_text(
            "🐙 <b>GitHub Access Token Required</b>\n\n"
            "To delete branches from your GitHub repository, please connect your GitHub PAT token in /settings first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]])
        )
        return

    raw_url = None
    if len(message.command) > 1:
        raw_url = message.command[1].strip()
    elif message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        parsed = DockerInspector.parse_github_url(reply_text)
        if parsed:
            raw_url = f"https://github.com/{parsed[0]}/{parsed[1]}"

    if not raw_url:
        DELETE_BRANCHES_SESSIONS[user_id] = {"step": "AWAIT_REPO_URL"}
        await message.reply_text(
            "🗑 <b>Delete Branches (/delete_branches)</b>\n\n"
            "Please send the GitHub Repository URL or owner/repo name:\n"
            "<i>Examples: https://github.com/owner/repository OR owner/repository</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_del_branches")]])
        )
        return

    await init_branch_deletion_wizard(client, message.chat.id, user_id, raw_url)

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "create_repo", "zip", "repos", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "delete_branches", "env", "env_converter", "settings"]) & auth_filter, group=4)
async def delete_branches_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = DELETE_BRANCHES_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_REPO_URL":
        message.continue_propagation()
        return

    text = message.text.strip()
    await init_branch_deletion_wizard(client, message.chat.id, user_id, text)

async def init_branch_deletion_wizard(client: Client, chat_id: int, user_id: int, input_text: str):
    parsed = DockerInspector.parse_github_url(input_text)
    if not parsed:
        await client.send_message(chat_id, "❌ Invalid repository URL or format. Please send in format: <code>owner/repository</code> or full GitHub URL.")
        return

    owner, repo = parsed
    gh_token = await db.get_user_github_token(user_id)

    msg = await client.send_message(chat_id, f"🔍 Fetching branches for <code>{owner}/{repo}</code>...")
    branches = await DockerInspector.fetch_repo_branches(owner, repo, github_token=gh_token)

    if not branches:
        await msg.edit_text(
            f"❌ <b>No branches found or failed to fetch for {owner}/{repo}.</b>\n\n"
            f"Please ensure the repository exists and your GitHub token in /settings has write/admin permissions.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]])
        )
        return

    DELETE_BRANCHES_SESSIONS[user_id] = {
        "owner": owner,
        "repo": repo,
        "branches": branches,
        "selected": set(),
        "page": 0
    }

    await msg.edit_text(
        f"🗑 <b>Delete Branches for <code>{owner}/{repo}</code> ({len(branches)} Total):</b>\n\n"
        f"Select the branch(es) you wish to permanently delete:",
        reply_markup=build_delete_branches_keyboard(user_id)
    )

@Client.on_callback_query(filters.regex("^del_br_item_(\\d+)$") & auth_filter)
async def del_br_item_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    session = DELETE_BRANCHES_SESSIONS.get(user_id)
    if not session or "branches" not in session:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    branches = session.get("branches", [])
    if 0 <= idx < len(branches):
        branch_name = branches[idx]
        selected = session["selected"]
        if branch_name in selected:
            selected.remove(branch_name)
        else:
            selected.add(branch_name)

    await callback_query.message.edit_reply_markup(reply_markup=build_delete_branches_keyboard(user_id))

@Client.on_callback_query(filters.regex("^del_br_toggle_all$") & auth_filter)
async def del_br_toggle_all_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DELETE_BRANCHES_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    branches = session.get("branches", [])
    selected = session["selected"]

    if len(selected) == len(branches):
        session["selected"] = set()
    else:
        session["selected"] = set(branches)

    await callback_query.message.edit_reply_markup(reply_markup=build_delete_branches_keyboard(user_id))

@Client.on_callback_query(filters.regex("^del_br_page_(\\d+)$") & auth_filter)
async def del_br_page_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    session = DELETE_BRANCHES_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    session["page"] = page
    await callback_query.message.edit_reply_markup(reply_markup=build_delete_branches_keyboard(user_id))

@Client.on_callback_query(filters.regex("^cancel_del_branches$") & auth_filter)
async def cancel_del_branches_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    DELETE_BRANCHES_SESSIONS.pop(user_id, None)
    await callback_query.message.edit_text("❌ Branch deletion canceled.")

@Client.on_callback_query(filters.regex("^del_br_confirm$") & auth_filter)
async def del_br_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DELETE_BRANCHES_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    selected = session.get("selected", set())
    if not selected:
        await callback_query.answer("Please select at least one branch to delete.", show_alert=True)
        return

    owner = session["owner"]
    repo = session["repo"]

    lines = [f"• <code>{b}</code>" for b in selected]
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ YES, DELETE PERMANENTLY", callback_data="del_br_execute"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_del_branches")
        ]
    ])

    await callback_query.message.edit_text(
        f"⚠️ <b>CONFIRM BRANCH DELETION</b>\n\n"
        f"<b>Repository:</b> <code>{owner}/{repo}</code>\n"
        f"<b>Selected Branches ({len(selected)}):</b>\n" + "\n".join(lines[:10]) + "\n\n"
        f"Are you sure you want to permanently delete these branches from GitHub?",
        reply_markup=kb
    )

@Client.on_callback_query(filters.regex("^del_br_execute$") & auth_filter)
async def del_br_execute_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = DELETE_BRANCHES_SESSIONS.get(user_id)
    if not session:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    owner = session["owner"]
    repo = session["repo"]
    selected = list(session.get("selected", set()))
    gh_token = await db.get_user_github_token(user_id)

    msg = await callback_query.message.edit_text(f"⏳ Deleting {len(selected)} branch(es) from <code>{owner}/{repo}</code>...")

    deleted_count = 0
    failed_count = 0
    deleted_list = []

    for b in selected:
        success = await DockerInspector.delete_repo_branch(owner, repo, b, gh_token)
        if success:
            deleted_count += 1
            deleted_list.append(b)
        else:
            failed_count += 1

    DELETE_BRANCHES_SESSIONS.pop(user_id, None)

    summary_lines = [
        f"✅ <b>Branch Deletion Summary for <code>{owner}/{repo}</code>:</b>\n",
        f"<b>Successfully Deleted:</b> {deleted_count} branch(es)",
        f"<b>Failed:</b> {failed_count} branch(es)\n"
    ]

    if deleted_list:
        summary_lines.append("<b>Deleted Branches:</b>")
        for b in deleted_list:
            summary_lines.append(f"• <code>{b}</code>")

    await msg.edit_text(
        "\n".join(summary_lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
    )
