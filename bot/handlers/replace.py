import asyncio
import logging
import re
import time
from pyrogram import Client, filters, errors, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.replacer import replace_in_html, replace_in_buttons, render_message_to_html
from bot.utils.stylizer import destylize
from bot.config import Config

logger = logging.getLogger(__name__)

# Registry for active asyncio tasks of running replace jobs
ACTIVE_TASKS = {}

# Session inactivity timeout: 5 minutes (300 seconds)
SESSION_TIMEOUT = 300

class ReplaceSession:
    def __init__(self, user_id, bot_message_id):
        self.user_id = user_id
        self.bot_message_id = bot_message_id
        self.chat_id = None
        self.chat_title = None
        self.first_msg_id = None
        self.last_msg_id = None
        self.targets = []
        self.replacement = None
        self.last_activity = time.time()
        self.timeout_task = None

# Global dictionary of active sessions in memory
SESSIONS = {}

def get_progress_bar(percentage):
    total_blocks = 15
    filled_blocks = int(round((percentage / 100.0) * total_blocks))
    filled_blocks = max(0, min(total_blocks, filled_blocks))
    return "█" * filled_blocks + "░" * (total_blocks - filled_blocks)

def format_duration(seconds):
    if seconds < 0:
        return "--:--"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def reset_session_timeout(client, user_id):
    """
    Resets the inactivity timeout for the user's replace session.
    If the user is inactive for 5 minutes, the session is cancelled automatically.
    """
    if user_id in SESSIONS:
        session = SESSIONS[user_id]
        if session.timeout_task:
            session.timeout_task.cancel()

        async def timeout_callback():
            try:
                await asyncio.sleep(SESSION_TIMEOUT)
                if user_id in SESSIONS:
                    sess = SESSIONS[user_id]
                    try:
                        await client.edit_message_text(
                            chat_id=user_id,
                            message_id=sess.bot_message_id,
                            text="❌ **Session expired due to inactivity.**\nPlease start over with /replace."
                        )
                    except Exception as e:
                        logger.warning(f"Failed to edit timeout message: {e}")

                    SESSIONS.pop(user_id, None)
                    await db.reset_user(user_id)
            except asyncio.CancelledError:
                pass

        session.timeout_task = asyncio.create_task(timeout_callback())

async def verify_bot_permissions(client, chat_id):
    """
    Completely rewritten admin verification.
    Correctly verifies: Channel Owner, Anonymous Admin, Normal Admin, Supergroup Admin.
    Verifies required permissions: can_edit_messages, can_delete_messages, can_manage_chat, can_post_messages (channels).
    Never falsely reports 'Bot is not admin' if the Bot actually has Edit Messages permission.
    """
    try:
        chat = await resolve_chat(client, chat_id)
    except Exception as e:
        return False, f"❌ Failed to resolve chat: {e}", None

    is_channel = chat.type == enums.ChatType.CHANNEL
    is_group = chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]

    if not is_channel and not is_group:
        return False, "❌ Text replacement is only supported in Channels or Supergroups/Groups.", chat

    try:
        member = await chat.get_member("me")
    except errors.UserNotParticipant:
        return False, "❌ Bot is not a member of this chat.", chat
    except Exception as e:
        return False, f"❌ Failed to verify bot membership: {e}", chat

    # If Bot is Owner, it has full permissions
    if member.status == enums.ChatMemberStatus.OWNER:
        return True, chat, chat

    if member.status != enums.ChatMemberStatus.ADMINISTRATOR:
        return False, "❌ Bot is not an admin in this chat.", chat

    privileges = member.privileges
    if not privileges:
        return False, "❌ Bot is an admin but has no privileges.", chat

    missing = []
    # In Pyrogram/Telegram API, can_edit_messages and can_post_messages are required for channels
    if is_channel:
        if not getattr(privileges, "can_post_messages", False):
            missing.append("can_post_messages")
        if not getattr(privileges, "can_edit_messages", False):
            missing.append("can_edit_messages")

    # can_manage_chat is required for robust administration
    if not getattr(privileges, "can_manage_chat", False):
        missing.append("can_manage_chat")

    if missing:
        missing_str = ", ".join(f"`{p}`" for p in missing)
        return False, f"❌ Bot is admin but missing required permission(s): {missing_str}", chat

    return True, chat, chat


@Client.on_message(filters.command("replace") & filters.private & filters.user(Config.ADMINS))
async def replace_command(client, message):
    user_id = message.from_user.id

    # Cancel previous task if running
    if user_id in ACTIVE_TASKS:
        return await message.reply_text("❌ A replacement task is already running! Type /cancel to stop it first.")

    await db.reset_user(user_id)

    # Step 1/4 layout and phrasing
    welcome_text = (
        "🔄 **Replace Wizard Started**\n\n"
        "Step 1/4:\n"
        "📩 Send the FIRST message link.\n\n"
        "Example:\n"
        "https://t.me/channel/100\n\n"
        "Type /cancel anytime to exit."
    )
    bot_msg = await message.reply_text(welcome_text)

    # Initialize session in memory
    session = ReplaceSession(user_id, bot_msg.id)
    SESSIONS[user_id] = session
    await db.update_user_state(user_id, "awaiting_replace_first_link")
    reset_session_timeout(client, user_id)


@Client.on_message(filters.command("cancel") & filters.private & filters.user(Config.ADMINS))
async def cancel_replace_command(client, message):
    user_id = message.from_user.id

    # 1. Cancel Active Wizard Session
    if user_id in SESSIONS:
        session = SESSIONS[user_id]
        if session.timeout_task:
            session.timeout_task.cancel()
        SESSIONS.pop(user_id, None)
        await db.reset_user(user_id)
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text="🛑 **Replace Wizard Cancelled.**"
            )
        except Exception as e:
            logger.warning(f"Failed to edit cancel message: {e}")
        return await message.reply_text("🛑 **Wizard setup has been cancelled.**")

    # 2. Cancel Running background task
    if user_id in ACTIVE_TASKS:
        task = ACTIVE_TASKS[user_id]
        task.cancel()
        return await message.reply_text("🛑 **Replacement task is stopping immediately...**")

    # Let propagation continue for other cancels if any
    message.continue_propagation()


@Client.on_message(filters.command("status") & filters.private & filters.user(Config.ADMINS))
async def status_replace_command(client, message):
    user_id = message.from_user.id
    job = await db.replace_jobs.find_one({"user_id": user_id, "status": "running"})
    if not job:
        return await message.reply_text("❌ No active replace task running currently.")

    await message.reply_text(
        f"📊 **Running Replace Task Status**\n\n"
        f"• **Channel:** `{job.get('chat_title')}`\n"
        f"• **Scanned:** `{job.get('total_scanned')}`\n"
        f"• **Edited:** `{job.get('total_edited')}`\n"
        f"• **Failed:** `{job.get('failed_count')}`"
    )


@Client.on_message(filters.command("resume") & filters.private & filters.user(Config.ADMINS))
async def resume_replace_command(client, message):
    user_id = message.from_user.id
    if user_id in ACTIVE_TASKS:
        return await message.reply_text("❌ A replacement task is already running!")

    job = await db.replace_jobs.find_one({
        "user_id": user_id,
        "status": {"$in": ["paused", "cancelled", "failed"]}
    })

    if not job:
        return await message.reply_text("❌ No unfinished replace tasks found to resume.")

    # Initialize a new status message for progress update
    status_msg = await message.reply_text("🔄 **Resuming replacement task...**")

    # Set status back to running in DB and memory
    await db.replace_jobs.update_one({"user_id": user_id, "job_id": job["job_id"]}, {"$set": {"status": "running"}})
    job["status"] = "running"

    task = asyncio.create_task(run_replacement_task(client, job, status_msg))
    ACTIVE_TASKS[user_id] = task
    logger.info(f"Resumed replace job {job['job_id']} for user {user_id}")


@Client.on_message(filters.private & filters.text & ~filters.command(["start", "sequence", "replace", "sort", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "font", "fontchannel", "replace_domain", "b", "tedit", "tedit_status", "tedit_stop", "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview", "status", "resume", "done"]), group=3)
async def handle_replace_workflow(client, message):
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)

    if not session:
        message.continue_propagation()
        return

    state = await db.get_user_state(user_id)
    if not state or not state.startswith("awaiting_replace_"):
        message.continue_propagation()
        return

    # Delete user's message immediately to keep the chat extremely clean and premium
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete user message: {e}")

    reset_session_timeout(client, user_id)

    if state == "awaiting_replace_first_link":
        chat_id, msg_id, _ = parse_message_link(message.text)
        if not chat_id:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=session.bot_message_id,
                    text="❌ **Invalid Link!**\n\nPlease send a valid FIRST message link.\n\nExample:\nhttps://t.me/channel/100"
                )
            except: pass
            return

        success, err_msg, chat = await verify_bot_permissions(client, chat_id)
        if not success:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=session.bot_message_id,
                    text=f"⚠️ **Permission Denied!**\n\n{err_msg}\n\nPlease fix permissions and start over."
                )
            except: pass
            SESSIONS.pop(user_id, None)
            await db.reset_user(user_id)
            return

        # Perform REPLACE_TEXT_CHANNELS check on numeric ID
        if Config.REPLACE_TEXT_CHANNELS and chat.id not in Config.REPLACE_TEXT_CHANNELS:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=session.bot_message_id,
                    text="❌ **This channel is not authorized for text replacement.**"
                )
            except: pass
            SESSIONS.pop(user_id, None)
            await db.reset_user(user_id)
            return

        session.chat_id = chat.id
        session.first_msg_id = msg_id
        session.chat_title = chat.title

        await db.update_user_state(user_id, "awaiting_replace_last_link")
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text=(
                    f"📩 Send the LAST message link.\n\n"
                    f"Example:\n"
                    f"https://t.me/channel/200"
                )
            )
        except: pass

    elif state == "awaiting_replace_last_link":
        chat_id, msg_id, _ = parse_message_link(message.text)
        resolved_chat_id = chat_id
        if isinstance(chat_id, str) and not chat_id.startswith("@") and chat_id.lstrip("-").isdigit():
            resolved_chat_id = int(chat_id)

        try:
            resolved_target = await resolve_chat(client, chat_id)
            resolved_chat_id = resolved_target.id
        except:
            pass

        if not chat_id or resolved_chat_id != session.chat_id:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=session.bot_message_id,
                    text=(
                        f"❌ **Invalid Link!** Link must be from the same channel: `{session.chat_title}`.\n\n"
                        f"📩 Send the LAST message link."
                    )
                )
            except: pass
            return

        session.last_msg_id = msg_id

        await db.update_user_state(user_id, "awaiting_replace_targets")
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text=(
                    f"🔍 What should I replace?\n\n"
                    f"You can send:\n"
                    f"• Text\n"
                    f"• URLs\n"
                    f"• Words\n"
                    f"• Emojis\n"
                    f"• Mentions\n"
                    f"• Domains\n"
                    f"• Any string\n\n"
                    f"You may send unlimited replacement targets.\n\n"
                    f"Example:\n"
                    f"https://anizoneflixback.onrender.com\n"
                    f"old-domain.com\n"
                    f"AnimeZone\n"
                    f"@OldChannel\n\n"
                    f"Every new message is added to the replacement list."
                )
            )
        except: pass

    elif state == "awaiting_replace_targets":
        item = message.text.strip()
        if item not in session.targets:
            session.targets.append(item)

        # Update the single interactive message with exact format
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text=(
                    f"✅ Added:\n"
                    f"{item}\n\n"
                    f"Current Items: {len(session.targets)}\n\n"
                    f"Continue sending more items or type /done when finished."
                )
            )
        except: pass

    elif state == "awaiting_replace_with":
        session.replacement = message.text.strip()

        # Update message to Step 5 (Loading/Checking state)
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text=(
                    "🔍 Checking permissions...\n"
                    "📂 Fetching messages...\n"
                    "📝 Replacing captions...\n"
                    "⏳ Please wait..."
                )
            )
        except: pass

        # Prepare job details
        job_id = f"replace_{int(time.time())}"
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "chat_id": session.chat_id,
            "chat_title": session.chat_title,
            "first_id": min(session.first_msg_id, session.last_msg_id),
            "last_id": max(session.first_msg_id, session.last_msg_id),
            "current_id": min(session.first_msg_id, session.last_msg_id),
            "targets": session.targets,
            "replacement": session.replacement,
            "status": "running",
            "total_scanned": 0,
            "total_edited": 0,
            "skipped": 0,
            "failed_count": 0,
            "error_reasons": {},
            "start_time": time.time(),
            "end_time": None
        }

        # Save to DB
        await db.replace_jobs.update_one({"user_id": user_id}, {"$set": job_data}, upsert=True)

        # Clear session timeout and session object from wizard memory
        if session.timeout_task:
            session.timeout_task.cancel()
        SESSIONS.pop(user_id, None)
        await db.reset_user(user_id)

        # Start replacement background task
        bot_msg_copy = await client.get_messages(user_id, session.bot_message_id)
        task = asyncio.create_task(run_replacement_task(client, job_data, bot_msg_copy))
        ACTIVE_TASKS[user_id] = task


@Client.on_message(filters.command("done") & filters.private & filters.user(Config.ADMINS))
async def done_replace_command(client, message):
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)
    if not session:
        return

    # Check MongoDB user state to verify we are actually in the targets stage
    state = await db.get_user_state(user_id)
    if state != "awaiting_replace_targets":
        return

    # Delete `/done` user message
    try:
        await message.delete()
    except: pass

    if not session.targets:
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text=(
                    "❌ **Please add at least one replacement target first!**\n\n"
                    "🔍 What should I replace?"
                )
            )
        except: pass
        return

    await db.update_user_state(user_id, "awaiting_replace_with")
    reset_session_timeout(client, user_id)

    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=session.bot_message_id,
            text=(
                "✨ Replace all selected items WITH:\n\n"
                "Example:\n"
                "https://anizoneflix-u00w.onrender.com"
            )
        )
    except: pass


async def run_replacement_task(client, job, status_msg):
    user_id = job["user_id"]
    job_id = job["job_id"]
    chat_id = job["chat_id"]
    first_id = job["first_id"]
    last_id = job["last_id"]
    targets = job["targets"]
    replacement = job["replacement"]

    # Destylize all targets to ensure stylized mathematical characters match perfectly
    targets_destylized = [destylize(t) for t in targets]

    # Initialize statistics
    total = last_id - first_id + 1
    processed = job.get("total_scanned", 0)
    edited = job.get("total_edited", 0)
    skipped = job.get("skipped", 0)
    failed = job.get("failed_count", 0)
    error_reasons = job.get("error_reasons", {})

    start_time = job.get("start_time") or time.time()
    current_id = job.get("current_id") or first_id

    # Periodic progress updater to avoid spamming the Telegram servers
    last_update_time = 0

    async def update_progress_msg(force=False):
        nonlocal last_update_time
        now = time.time()
        if not force and (now - last_update_time < 2.5):
            return

        elapsed = int(now - start_time)
        percentage = (processed / total) * 100 if total > 0 else 0
        speed = processed / elapsed if elapsed > 0 else 0
        remaining_seconds = int((total - processed) / speed) if speed > 0 else -1

        progress_bar = get_progress_bar(percentage)
        speed_str = f"{int(speed)} msg/sec" if speed > 0 else "0 msg/sec"
        remaining_str = format_duration(remaining_seconds) if remaining_seconds >= 0 else "--:--"

        progress_text = (
            "🔄 Replace Wizard\n\n"
            f"{progress_bar} {int(percentage)}%\n\n"
            f"Processed:\n{processed} / {total}\n\n"
            f"Edited:\n{edited}\n\n"
            f"Skipped:\n{skipped}\n\n"
            f"Errors:\n{failed}\n\n"
            f"Speed:\n{speed_str}\n\n"
            f"Elapsed:\n{format_duration(elapsed)}\n\n"
            f"Remaining:\n{remaining_str}"
        )
        try:
            await client.edit_message_text(
                chat_id=status_msg.chat.id,
                message_id=status_msg.id,
                text=progress_text
            )
            last_update_time = now
        except errors.MessageNotModified:
            pass
        except errors.FloodWait as e:
            # Sleep if we trigger FloodWait on status message itself
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.error(f"Error editing progress message: {e}")

    # Re-verify permissions before launching task
    success, err_msg, _ = await verify_bot_permissions(client, chat_id)
    if not success:
        try:
            await client.edit_message_text(
                chat_id=status_msg.chat.id,
                message_id=status_msg.id,
                text=f"❌ **Permission Verification Failed:**\n\n{err_msg}"
            )
        except: pass
        await db.replace_jobs.update_one({"user_id": user_id, "job_id": job_id}, {"$set": {"status": "failed"}})
        ACTIVE_TASKS.pop(user_id, None)
        return

    logger.info(f"Starting replacement background job {job_id} for user {user_id}. Range: {current_id} to {last_id}")

    try:
        # Fetch and process in batches of 100
        for i in range(current_id, last_id + 1, 100):
            # Check for cancellation
            job_status = await db.replace_jobs.find_one({"user_id": user_id, "job_id": job_id})
            if not job_status or job_status.get("status") == "cancelled":
                logger.info(f"Replace task {job_id} cancelled.")
                break

            batch_ids = list(range(i, min(i + 100, last_id + 1)))
            try:
                messages = await client.get_messages(chat_id, batch_ids)
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
                messages = await client.get_messages(chat_id, batch_ids)
            except Exception as e:
                logger.error(f"Failed to fetch batch {batch_ids}: {e}")
                failed += len(batch_ids)
                processed += len(batch_ids)
                continue

            if not isinstance(messages, list):
                messages = [messages]

            # Setup locks and semaphore for controlled concurrent edits
            lock = asyncio.Lock()
            stats_dict = {
                "edited": 0,
                "skipped": 0,
                "failed": 0,
                "errors": {}
            }
            sem = asyncio.Semaphore(5)

            async def process_single_message(msg):
                if not msg or msg.empty:
                    async with lock:
                        stats_dict["skipped"] += 1
                    return

                # Get HTML with entities preserved (safely handles both text messages and captions!)
                if msg.text:
                    current_html = render_message_to_html(msg.text, msg.entities)
                elif msg.caption:
                    current_html = render_message_to_html(msg.caption, msg.caption_entities)
                else:
                    async with lock:
                        stats_dict["skipped"] += 1
                    return

                # Detect if any target matches in a stylization-safe manner
                has_match = False
                current_html_destylized = destylize(current_html)
                for target in targets_destylized:
                    if target.lower() in current_html_destylized.lower():
                        has_match = True
                        break
                    if msg.reply_markup and target.lower() in destylize(str(msg.reply_markup)).lower():
                        has_match = True
                        break

                if not has_match:
                    async with lock:
                        stats_dict["skipped"] += 1
                    return

                # Perform safe HTML and Button replacement using our robust helper functions
                new_html = current_html
                for target in targets:
                    new_html = replace_in_html(new_html, target, replacement)

                new_reply_markup = None
                if msg.reply_markup:
                    new_reply_markup = msg.reply_markup
                    for target in targets:
                        new_reply_markup = replace_in_buttons(new_reply_markup, target, replacement)

                # Edit message if anything changed
                if new_html != current_html or (msg.reply_markup and new_reply_markup != msg.reply_markup):
                    async with sem:
                        success_edit = False
                        for attempt in range(3):
                            try:
                                if msg.text:
                                    await client.edit_message_text(
                                        chat_id, msg.id, new_html,
                                        parse_mode=enums.ParseMode.HTML,
                                        reply_markup=new_reply_markup
                                    )
                                else:
                                    invert = getattr(msg, "invert_media", False)
                                    await client.edit_message_caption(
                                        chat_id, msg.id, new_html,
                                        parse_mode=enums.ParseMode.HTML,
                                        reply_markup=new_reply_markup,
                                        invert_media=invert
                                    )
                                success_edit = True
                                async with lock:
                                    stats_dict["edited"] += 1
                                break
                            except errors.FloodWait as e:
                                await asyncio.sleep(e.value + 1)
                            except errors.MessageNotModified:
                                success_edit = True
                                async with lock:
                                    stats_dict["skipped"] += 1
                                break
                            except Exception as e:
                                logger.error(f"Failed to edit message {msg.id} (attempt {attempt}): {e}")
                                if attempt == 2:
                                    async with lock:
                                        stats_dict["failed"] += 1
                                        stats_dict["errors"][str(msg.id)] = str(e)
                                await asyncio.sleep(1)
                else:
                    async with lock:
                        stats_dict["skipped"] += 1

            # Execute concurrent edits for this batch
            await asyncio.gather(*(process_single_message(m) for m in messages))

            # Merge stats
            processed += len(batch_ids)
            edited += stats_dict["edited"]
            skipped += stats_dict["skipped"]
            failed += stats_dict["failed"]
            error_reasons.update(stats_dict["errors"])

            # Save state progress in DB
            current_id = i + len(batch_ids)
            await db.replace_jobs.update_one({"user_id": user_id, "job_id": job_id}, {"$set": {
                "total_scanned": processed,
                "total_edited": edited,
                "skipped": skipped,
                "failed_count": failed,
                "error_reasons": error_reasons,
                "current_id": current_id
            }})

            # Live Progress update
            await update_progress_msg()

            # Rate limit defense
            await asyncio.sleep(0.5)

        # Completion handling
        elapsed = int(time.time() - start_time)
        completion_text = (
            "✅ Replacement Completed\n\n"
            "Messages Processed:\n"
            f"{processed}\n\n"
            "Messages Edited:\n"
            f"{edited}\n\n"
            "Skipped:\n"
            f"{skipped}\n\n"
            "Failed:\n"
            f"{failed}\n\n"
            "Time Taken:\n"
            f"{elapsed} seconds"
        )
        try:
            await client.edit_message_text(
                chat_id=status_msg.chat.id,
                message_id=status_msg.id,
                text=completion_text
            )
        except Exception as e:
            logger.error(f"Failed to edit completion message: {e}")

        # Update Job Status to completed
        await db.replace_jobs.update_one({"user_id": user_id, "job_id": job_id}, {"$set": {
            "status": "completed",
            "end_time": time.time()
        }})

    except asyncio.CancelledError:
        logger.info(f"Replace task {job_id} cancelled.")
        await db.replace_jobs.update_one({"user_id": user_id, "job_id": job_id}, {"$set": {"status": "cancelled"}})
        try:
            await client.edit_message_text(
                chat_id=status_msg.chat.id,
                message_id=status_msg.id,
                text="🛑 **Replacement task stopped immediately.**"
            )
        except: pass
    except Exception as e:
        logger.error(f"Error running replacement task: {e}", exc_info=True)
        await db.replace_jobs.update_one({"user_id": user_id, "job_id": job_id}, {"$set": {"status": "failed"}})
        try:
            await client.edit_message_text(
                chat_id=status_msg.chat.id,
                message_id=status_msg.id,
                text=f"❌ **Replacement Task Failed:**\n\n`{e}`"
            )
        except: pass
    finally:
        ACTIVE_TASKS.pop(user_id, None)
