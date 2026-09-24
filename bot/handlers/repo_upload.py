import os
import shutil
import tempfile
import zipfile
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.mongo import db
from bot.utils.security import auth_filter, mask_secret
from bot.utils.docker_inspector import DockerInspector

logger = logging.getLogger(__name__)

REPO_UPLOAD_SESSIONS: Dict[int, Dict[str, Any]] = {}

ALL_COMMANDS = [
    "start", "help", "deploy", "create_repo", "zip", "repo_upload", "repos",
    "projects", "status", "logs", "restart", "redeploy", "redeploy_all",
    "stop", "delete", "env", "env_converter", "delete_branches", "settings"
]

def cleanup_upload_session(user_id: int):
    session = REPO_UPLOAD_SESSIONS.pop(user_id, None)
    if session and "temp_dir" in session and session["temp_dir"]:
        try:
            shutil.rmtree(session["temp_dir"], ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to cleanup temp_dir for user {user_id}: {e}")

async def create_github_branch_api(owner: str, repo: str, branch: str, token: str) -> bool:
    """Create a new branch on GitHub using the REST API if it doesn't already exist."""
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RenderDeployerBot"
    }

    async with aiohttp.ClientSession() as session:
        # Check if branch already exists
        check_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
        try:
            async with session.get(check_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(f"Branch {branch} already exists on {owner}/{repo}")
                    return True
        except Exception as e:
            logger.warning(f"Error checking branch status: {e}")

        # Get default branch SHA
        repo_url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            async with session.get(repo_url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return False
                repo_info = await resp.json()
                default_branch = repo_info.get("default_branch", "main")

            ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{default_branch}"
            async with session.get(ref_url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return False
                ref_info = await resp.json()
                sha = ref_info.get("object", {}).get("sha")

            if sha:
                create_ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
                payload = {"ref": f"refs/heads/{branch}", "sha": sha}
                async with session.post(create_ref_url, headers=headers, json=payload, timeout=10) as resp:
                    if resp.status in [200, 201]:
                        logger.info(f"Successfully created branch {branch} via GitHub API")
                        return True
                    else:
                        data = await resp.json()
                        logger.warning(f"GitHub API branch creation response {resp.status}: {data}")
        except Exception as e:
            logger.error(f"Error creating branch via GitHub API: {e}")

    return False

async def upload_via_github_api(
    extract_dir: str,
    owner: str,
    repo: str,
    branch: str,
    token: str
) -> Tuple[bool, str]:
    """Fallback method using GitHub REST API Git Trees to commit and push files if Git CLI is unavailable."""
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RenderDeployerBot"
    }

    async with aiohttp.ClientSession() as session:
        try:
            # 1. Get latest commit SHA on branch
            ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch}"
            async with session.get(ref_url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return False, f"Could not find branch ref for '{branch}' on GitHub."
                ref_data = await resp.json()
                commit_sha = ref_data.get("object", {}).get("sha")

            # 2. Get tree SHA for that commit
            commit_url = f"https://api.github.com/repos/{owner}/{repo}/git/commits/{commit_sha}"
            async with session.get(commit_url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return False, "Could not fetch commit object."
                commit_data = await resp.json()
                base_tree_sha = commit_data.get("tree", {}).get("sha")

            # 3. Create blobs for each file
            tree_items = []
            for root, _, files in os.walk(extract_dir):
                for file_name in files:
                    full_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(full_path, extract_dir).replace("\\", "/")
                    if rel_path.startswith(".git"):
                        continue

                    try:
                        with open(full_path, "rb") as f:
                            content_bytes = f.read()

                        import base64
                        b64_content = base64.b64encode(content_bytes).decode("utf-8")

                        blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs"
                        blob_payload = {"content": b64_content, "encoding": "base64"}
                        async with session.post(blob_url, headers=headers, json=blob_payload, timeout=15) as b_resp:
                            if b_resp.status not in [200, 201]:
                                continue
                            b_data = await b_resp.json()
                            blob_sha = b_data.get("sha")

                        tree_items.append({
                            "path": rel_path,
                            "mode": "100644",
                            "type": "blob",
                            "sha": blob_sha
                        })
                    except Exception as e_f:
                        logger.warning(f"Failed to create blob for {rel_path}: {e_f}")

            if not tree_items:
                return False, "No valid files found in extracted archive to commit."

            # 4. Create new tree
            create_tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees"
            tree_payload = {"base_tree": base_tree_sha, "tree": tree_items}
            async with session.post(create_tree_url, headers=headers, json=tree_payload, timeout=20) as t_resp:
                if t_resp.status not in [200, 201]:
                    return False, "Failed to create Git tree via GitHub API."
                t_data = await t_resp.json()
                new_tree_sha = t_data.get("sha")

            # 5. Create new commit
            create_commit_url = f"https://api.github.com/repos/{owner}/{repo}/git/commits"
            c_payload = {
                "message": f"Upload repository files to {branch} via Telegram Bot (API Fallback)",
                "tree": new_tree_sha,
                "parents": [commit_sha]
            }
            async with session.post(create_commit_url, headers=headers, json=c_payload, timeout=15) as c_resp:
                if c_resp.status not in [200, 201]:
                    return False, "Failed to create commit via GitHub API."
                c_data = await c_resp.json()
                new_commit_sha = c_data.get("sha")

            # 6. Update branch reference
            update_ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}"
            update_payload = {"sha": new_commit_sha, "force": True}
            async with session.patch(update_ref_url, headers=headers, json=update_payload, timeout=15) as u_resp:
                if u_resp.status == 200:
                    return True, f"Successfully uploaded files to branch '{branch}' via GitHub API."
                else:
                    return False, "Failed to update branch reference on GitHub."

        except Exception as e:
            logger.error(f"Error in upload_via_github_api: {e}")
            return False, str(e)

async def upload_extracted_files_to_branch(
    extract_dir: str,
    owner: str,
    repo: str,
    branch: str,
    username: str,
    token: str
) -> Tuple[bool, str]:
    """Clones/initializes repository, extracts zip contents, creates branch, and pushes changes using credentials."""
    work_dir = tempfile.mkdtemp(prefix="repo_upload_git_")
    auth_url = f"https://{username.strip()}:{token.strip()}@github.com/{owner}/{repo}.git"

    try:
        # Step 1: Attempt to clone existing repository
        try:
            clone_proc = await asyncio.create_subprocess_exec(
                "git", "clone", auth_url, work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError:
            logger.warning("Git CLI binary not found on system. Falling back to GitHub REST API...")
            return await upload_via_github_api(extract_dir, owner, repo, branch, token)
        _, stderr_clone = await clone_proc.communicate()

        is_cloned = (clone_proc.returncode == 0)

        if is_cloned:
            # Configure user in cloned repo
            await (await asyncio.create_subprocess_exec("git", "config", "user.name", username, cwd=work_dir)).wait()
            await (await asyncio.create_subprocess_exec("git", "config", "user.email", f"{username}@users.noreply.github.com", cwd=work_dir)).wait()

            # Checkout new branch (or switch to it)
            co_proc = await asyncio.create_subprocess_exec("git", "checkout", "-B", branch, cwd=work_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await co_proc.communicate()

            # Copy extracted files over repo directory
            for item in os.listdir(extract_dir):
                s = os.path.join(extract_dir, item)
                d = os.path.join(work_dir, item)
                if item == ".git":
                    continue
                if os.path.isdir(s):
                    if os.path.exists(d):
                        shutil.rmtree(d)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
        else:
            # Repository might be empty or new, initialize directly in extract_dir
            work_dir_to_use = extract_dir
            await (await asyncio.create_subprocess_exec("git", "init", cwd=work_dir_to_use)).wait()
            await (await asyncio.create_subprocess_exec("git", "config", "user.name", username, cwd=work_dir_to_use)).wait()
            await (await asyncio.create_subprocess_exec("git", "config", "user.email", f"{username}@users.noreply.github.com", cwd=work_dir_to_use)).wait()
            await (await asyncio.create_subprocess_exec("git", "checkout", "-B", branch, cwd=work_dir_to_use)).wait()

            # Set remote
            await (await asyncio.create_subprocess_exec("git", "remote", "remove", "origin", cwd=work_dir_to_use)).wait()
            await (await asyncio.create_subprocess_exec("git", "remote", "add", "origin", auth_url, cwd=work_dir_to_use)).wait()
            work_dir = work_dir_to_use

        # Stage all files
        add_proc = await asyncio.create_subprocess_exec("git", "add", "-A", cwd=work_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await add_proc.communicate()

        # Commit changes
        commit_proc = await asyncio.create_subprocess_exec("git", "commit", "-m", f"Upload repository files to {branch} via Telegram Bot", cwd=work_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await commit_proc.communicate()

        # Push to branch
        push_proc = await asyncio.create_subprocess_exec("git", "push", "-u", "origin", branch, "--force", cwd=work_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr_push = await push_proc.communicate()

        if push_proc.returncode == 0:
            return True, f"Successfully created branch '{branch}' and uploaded files to {owner}/{repo}."
        else:
            err_msg = stderr_push.decode().strip() or "Git push failed."
            return False, f"Git push error: {err_msg}"

    except Exception as e:
        logger.error(f"Error in upload_extracted_files_to_branch: {e}")
        return False, str(e)
    finally:
        if work_dir and os.path.exists(work_dir) and work_dir != extract_dir:
            shutil.rmtree(work_dir, ignore_errors=True)

@Client.on_message(filters.command("repo_upload") & auth_filter)
async def repo_upload_command(client: Client, message: Message):
    user_id = message.from_user.id
    cleanup_upload_session(user_id)

    REPO_UPLOAD_SESSIONS[user_id] = {"step": "AWAIT_ZIP"}

    await message.reply_text(
        "📦 <b>Upload Repository from ZIP (/repo_upload)</b>\n\n"
        "Please send or upload your project `.zip` archive file as a Telegram document.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_repo_upload")]
        ])
    )

@Client.on_callback_query(filters.regex("^cancel_repo_upload$") & auth_filter)
async def cancel_repo_upload_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    cleanup_upload_session(user_id)
    await callback_query.message.edit_text("❌ Repository upload flow canceled.")

@Client.on_message(filters.document & auth_filter, group=5)
async def upload_zip_document_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = REPO_UPLOAD_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_ZIP":
        message.continue_propagation()
        return

    doc = message.document
    if not doc or not (doc.file_name and doc.file_name.lower().endswith(".zip")):
        await message.reply_text("❌ Please upload a valid <code>.zip</code> file.")
        return

    status_msg = await message.reply_text("⏳ <b>Downloading and extracting ZIP archive...</b>")

    try:
        temp_dir = tempfile.mkdtemp(prefix="repo_upload_")
        zip_path = os.path.join(temp_dir, doc.file_name)

        await client.download_media(message, file_name=zip_path)

        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # If extracted folder has a single top-level directory, adjust extract_dir to it
        extracted_items = os.listdir(extract_dir)
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_items[0])):
            extract_dir = os.path.join(extract_dir, extracted_items[0])

        session["temp_dir"] = temp_dir
        session["extract_dir"] = extract_dir
        session["zip_name"] = doc.file_name
        session["step"] = "AWAIT_REPO"
        REPO_UPLOAD_SESSIONS[user_id] = session

        await status_msg.edit_text(
            f"✅ <b>Extracted ZIP:</b> <code>{doc.file_name}</code>\n\n"
            "Please send the target GitHub repository URL or name:\n"
            "<i>Examples: https://github.com/owner/repository OR owner/repository</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_repo_upload")]
            ])
        )

    except Exception as e:
        logger.error(f"Error handling zip upload document: {e}")
        cleanup_upload_session(user_id)
        await status_msg.edit_text(f"❌ <b>Failed to process ZIP file:</b> {str(e)}")

@Client.on_message(filters.text & ~filters.command(ALL_COMMANDS) & auth_filter, group=5)
async def repo_upload_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = REPO_UPLOAD_SESSIONS.get(user_id)
    if not session:
        message.continue_propagation()
        return

    step = session.get("step")
    text = message.text.strip()

    if step == "AWAIT_REPO":
        parsed = DockerInspector.parse_github_url(text)
        if not parsed:
            await message.reply_text(
                "❌ Invalid repository format.\n"
                "Please send in format: <code>owner/repository</code> or <code>https://github.com/owner/repository</code>"
            )
            return

        owner, repo = parsed
        session["owner"] = owner
        session["repo"] = repo
        session["repo_url"] = f"https://github.com/{owner}/{repo}"
        session["step"] = "AWAIT_BRANCH"

        await message.reply_text(
            f"✅ <b>Target Repo:</b> <code>{owner}/{repo}</code>\n\n"
            "Please enter the branch name to create and upload files to:\n"
            "<i>Examples: feature-upload, dev, main</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_repo_upload")]
            ])
        )

    elif step == "AWAIT_BRANCH":
        branch_name = text
        session["branch"] = branch_name

        # Check saved GitHub PAT token
        saved_token = await db.get_user_github_token(user_id)
        if saved_token:
            # Try fetching username for saved token
            fetched_username = None
            async with aiohttp.ClientSession() as http_sess:
                try:
                    async with http_sess.get("https://api.github.com/user", headers={"Authorization": f"Bearer {saved_token.strip()}"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            fetched_username = data.get("login")
                except Exception as e:
                    logger.warning(f"Failed to fetch GitHub username from saved token: {e}")

            if fetched_username:
                session["username"] = fetched_username
                session["token"] = saved_token
                session["step"] = "CONFIRMATION"

                await show_upload_confirmation(client, message.chat.id, user_id)
                return

        session["step"] = "AWAIT_USERNAME"
        await message.reply_text(
            "🔑 <b>GitHub Credentials Required</b>\n\n"
            "Please enter your GitHub Repo Username:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_repo_upload")]
            ])
        )

    elif step == "AWAIT_USERNAME":
        session["username"] = text
        session["step"] = "AWAIT_TOKEN"
        await message.reply_text(
            f"✅ <b>GitHub Username:</b> <code>{text}</code>\n\n"
            "Please enter your GitHub Personal Access Token (PAT):\n"
            "<i>Token requires repo write scope.</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_repo_upload")]
            ])
        )

    elif step == "AWAIT_TOKEN":
        session["token"] = text
        session["step"] = "CONFIRMATION"
        await show_upload_confirmation(client, message.chat.id, user_id)

async def show_upload_confirmation(client: Client, chat_id: int, user_id: int):
    session = REPO_UPLOAD_SESSIONS.get(user_id)
    if not session:
        return

    text = (
        "📋 <b>Repository Upload Confirmation</b>\n\n"
        f"<b>ZIP File:</b> <code>{session.get('zip_name', 'archive.zip')}</code>\n"
        f"<b>Target Repo:</b> <code>{session.get('owner')}/{session.get('repo')}</code>\n"
        f"<b>Branch to Create:</b> <code>{session.get('branch')}</code>\n"
        f"<b>GitHub Username:</b> <code>{session.get('username')}</code>\n"
        f"<b>Token:</b> <code>{mask_secret(session.get('token', ''))}</code>\n\n"
        "Click confirm to create the branch and upload files."
    )

    await client.send_message(
        chat_id,
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 Create Branch & Upload", callback_data="confirm_repo_upload"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_repo_upload")
            ]
        ])
    )

@Client.on_callback_query(filters.regex("^confirm_repo_upload$") & auth_filter)
async def confirm_repo_upload_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = REPO_UPLOAD_SESSIONS.get(user_id)
    if not session:
        await callback_query.message.edit_text("❌ Session expired. Please run /repo_upload again.")
        return

    status_msg = await callback_query.message.edit_text(
        f"⏳ <b>Creating branch '{session.get('branch')}' and uploading files to {session.get('owner')}/{session.get('repo')}...</b>"
    )

    owner = session["owner"]
    repo = session["repo"]
    branch = session["branch"]
    username = session["username"]
    token = session["token"]
    extract_dir = session["extract_dir"]

    # Try creating branch via GitHub API first
    await create_github_branch_api(owner, repo, branch, token)

    # Upload extracted files via Git CLI
    success, result_msg = await upload_extracted_files_to_branch(
        extract_dir, owner, repo, branch, username, token
    )

    cleanup_upload_session(user_id)

    if success:
        branch_url = f"https://github.com/{owner}/{repo}/tree/{branch}"
        text = (
            f"🎉 <b>Repository Upload Completed Successfully!</b>\n\n"
            f"<b>Repository:</b> <code>{owner}/{repo}</code>\n"
            f"<b>Branch Created:</b> <code>{branch}</code>\n"
            f"<b>URL:</b> {branch_url}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Deploy to Render", callback_data="start_deploy")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        await status_msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await status_msg.edit_text(
            f"❌ <b>Failed to upload repository:</b>\n{result_msg}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
        )
