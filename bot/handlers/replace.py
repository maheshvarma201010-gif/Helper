import asyncio
import logging
import re
import time
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from collections import deque

from pyrogram import Client, filters, errors, enums
from pyrogram.types import Message
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.config import Config

logger = logging.getLogger(__name__)

# Active tasks and sessions
ACTIVE_TASKS = {}
SESSIONS = {}

@dataclass
class ReplaceSession:
    """Session data for replacement wizard"""
    user_id: int
    bot_message_id: int
    chat_id: Optional[int] = None
    chat_title: Optional[str] = None
    first_msg_id: Optional[int] = None
    last_msg_id: Optional[int] = None
    targets: List[str] = field(default_factory=list)
    replacement: Optional[str] = None
    step: int = 1
    created_at: float = field(default_factory=time.time)

class ReplacementStats:
    """Comprehensive statistics"""
    def __init__(self):
        self.total = 0
        self.processed = 0
        self.edited = 0
        self.skipped_no_caption = 0
        self.skipped_no_target = 0
        self.skipped_unchanged = 0
        self.failed = 0
        self.start_time = time.time()
        self.end_time = None
        self.error_reasons: Dict[int, str] = {}
        self.found_targets: Dict[str, int] = {}
        self.replacements_made: Dict[str, int] = {}
        
    def get_speed(self) -> float:
        elapsed = time.time() - self.start_time
        return self.processed / elapsed if elapsed > 0 else 0
    
    def get_eta(self) -> str:
        speed = self.get_speed()
        if speed == 0:
            return "--:--"
        remaining = self.total - self.processed
        eta_seconds = int(remaining / speed)
        return format_duration(eta_seconds)
    
    def get_progress_bar(self, width=15) -> str:
        if self.total == 0:
            return "░" * width
        percentage = (self.processed / self.total) * 100
        filled = int(round((percentage / 100.0) * width))
        filled = max(0, min(width, filled))
        return "█" * filled + "░" * (width - filled)
    
    def get_percentage(self) -> int:
        return int((self.processed / self.total) * 100) if self.total > 0 else 0

def format_duration(seconds: int) -> str:
    if seconds < 0:
        return "--:--"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def parse_message_link(link: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Parse Telegram message link to extract chat_id and message_id
    Supports formats:
    - https://t.me/channel/100
    - https://t.me/c/123456789/100
    - https://t.me/username/100
    """
    if not link:
        return None, None, None
    
    link = link.strip()
    
    # Pattern for: https://t.me/channel/100 or https://t.me/username/100
    pattern1 = r'https?://t\.me/([^/]+)/(\d+)'
    match = re.search(pattern1, link)
    if match:
        chat_identifier = match.group(1)
        msg_id = int(match.group(2))
        return chat_identifier, msg_id, None
    
    # Pattern for: https://t.me/c/123456789/100
    pattern2 = r'https?://t\.me/c/(\d+)/(\d+)'
    match = re.search(pattern2, link)
    if match:
        chat_id = int(match.group(1))
        msg_id = int(match.group(2))
        return chat_id, msg_id, None
    
    # Try to extract from any URL with numbers
    pattern3 = r'https?://[^/]+/(?:c/)?(\d+)/(\d+)'
    match = re.search(pattern3, link)
    if match:
        chat_id = int(match.group(1))
        msg_id = int(match.group(2))
        return chat_id, msg_id, None
    
    return None, None, None

def extract_urls_from_text(text: str) -> List[Tuple[str, int, int]]:
    """
    Extract all URLs from text with their positions
    Returns: List of (url, start_pos, end_pos)
    """
    urls = []
    
    if not text:
        return urls
    
    # Pattern for markdown links: [text](url)
    markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    for match in re.finditer(markdown_pattern, text):
        url = match.group(2)
        if url.startswith(('http://', 'https://')):
            urls.append((url, match.start(2), match.end(2)))
    
    # Pattern for plain URLs
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    for match in re.finditer(url_pattern, text):
        url = match.group(0)
        # Check if this URL is already inside a markdown link
        is_inside_markdown = False
        for _, start, end in urls:
            if start <= match.start() <= end:
                is_inside_markdown = True
                break
        if not is_inside_markdown:
            urls.append((url, match.start(), match.end()))
    
    return urls

def normalize_url(url: str) -> str:
    """Normalize URL for comparison"""
    url = url.strip()
    # Remove trailing slash
    url = url.rstrip('/')
    # Remove www.
    url = re.sub(r'^https?://www\.', 'https://', url)
    # Normalize http vs https
    url = re.sub(r'^http://', 'https://', url)
    return url.lower()

def replace_urls_in_text(text: str, targets: List[str], replacement: str) -> Tuple[str, Dict[str, int]]:
    """
    Find and replace URLs in text
    Returns: (new_text, replacements_count)
    """
    if not text:
        return text, {}
    
    replacements_count = {}
    new_text = text
    
    # Sort targets by length (longest first)
    targets_sorted = sorted(targets, key=len, reverse=True)
    
    # Extract all URLs from text
    urls = extract_urls_from_text(text)
    
    # Check each URL against targets
    for url, start, end in urls:
        url_normalized = normalize_url(url)
        
        for target in targets_sorted:
            target_normalized = normalize_url(target)
            
            # Check if URL contains the target
            if target_normalized in url_normalized or url_normalized in target_normalized:
                # Replace the URL
                new_url = url.replace(target, replacement)
                new_text = new_text[:start] + new_url + new_text[end:]
                
                # Update counts
                replacements_count[target] = replacements_count.get(target, 0) + 1
                logger.info(f"Replaced URL: {url} -> {new_url}")
                break
    
    # Also do direct string replacement for any remaining targets
    for target in targets_sorted:
        if target in new_text:
            count = new_text.count(target)
            if count > 0:
                new_text = new_text.replace(target, replacement)
                replacements_count[target] = replacements_count.get(target, 0) + count
                logger.info(f"Direct replacement: {target} -> {replacement} ({count} times)")
    
    return new_text, replacements_count

async def verify_bot_permissions(client: Client, chat_id: Any) -> Tuple[bool, str, Optional[Any]]:
    """Verify bot permissions"""
    try:
        chat = await resolve_chat(client, chat_id)
    except Exception as e:
        return False, f"❌ Failed to resolve chat: {e}", None

    try:
        member = await chat.get_member("me")
    except errors.UserNotParticipant:
        return False, "❌ Bot is not a member of this chat.", chat
    except Exception as e:
        return False, f"❌ Failed to verify bot membership: {e}", chat

    if member.status == enums.ChatMemberStatus.OWNER:
        return True, "✅ Bot is channel owner", chat

    if member.status != enums.ChatMemberStatus.ADMINISTRATOR:
        return False, "❌ Bot is not an admin in this chat.", chat

    privileges = member.privileges
    if not privileges:
        return False, "❌ Bot has no privileges.", chat

    # Check required permissions
    is_channel = chat.type == enums.ChatType.CHANNEL
    missing = []
    
    if is_channel:
        if not getattr(privileges, "can_post_messages", False):
            missing.append("can_post_messages")
        if not getattr(privileges, "can_edit_messages", False):
            missing.append("can_edit_messages")
    else:
        if not getattr(privileges, "can_manage_chat", False):
            missing.append("can_manage_chat")
        if not getattr(privileges, "can_edit_messages", False):
            missing.append("can_edit_messages")

    if missing:
        return False, f"❌ Missing: {', '.join(missing)}", chat

    return True, "✅ All permissions verified", chat

async def edit_bot_message(client: Client, user_id: int, message_id: int, text: str):
    """Safely edit bot message"""
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=text
        )
        return True
    except errors.MessageNotModified:
        return True
    except Exception as e:
        logger.error(f"Failed to edit bot message: {e}")
        return False

@Client.on_message(filters.command("replace") & filters.private & filters.user(Config.ADMINS))
async def replace_command(client: Client, message: Message):
    """Start replacement wizard"""
    user_id = message.from_user.id

    if user_id in ACTIVE_TASKS:
        return await message.reply_text(
            "❌ A replacement task is already running!\n"
            "Type /cancel to stop it first."
        )

    if user_id in SESSIONS:
        SESSIONS.pop(user_id, None)
    
    await db.reset_user(user_id)

    welcome_text = (
        "🛠️ **Caption Replace Tool**\n\n"
        "📌 **Step 1/4:** Send the **FIRST** Telegram message link.\n\n"
        "Example:\n"
        "https://t.me/channel/100\n\n"
        "Type /cancel anytime to exit."
    )
    
    bot_msg = await message.reply_text(welcome_text)

    session = ReplaceSession(
        user_id=user_id,
        bot_message_id=bot_msg.id
    )
    SESSIONS[user_id] = session
    await db.update_user_state(user_id, "awaiting_replace_first_link")

@Client.on_message(filters.command("cancel") & filters.private & filters.user(Config.ADMINS))
async def cancel_replace_command(client: Client, message: Message):
    """Cancel wizard or task"""
    user_id = message.from_user.id

    if user_id in SESSIONS:
        session = SESSIONS[user_id]
        SESSIONS.pop(user_id, None)
        await db.reset_user(user_id)
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=session.bot_message_id,
                text="🛑 **Replace Wizard Cancelled.**"
            )
        except:
            pass
        return await message.reply_text("🛑 **Wizard cancelled.**")

    if user_id in ACTIVE_TASKS:
        task = ACTIVE_TASKS[user_id]
        task.cancel()
        await message.reply_text("🛑 **Replacement task stopping...**")
        return

    await message.reply_text("ℹ️ No active replace task found.")

@Client.on_message(filters.command("done") & filters.private & filters.user(Config.ADMINS))
async def done_replace_command(client: Client, message: Message):
    """Finish adding targets"""
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)
    
    if not session:
        return await message.reply_text("❌ No active replace session found.")

    state = await db.get_user_state(user_id)
    if state != "awaiting_replace_targets":
        return

    try:
        await message.delete()
    except:
        pass

    if not session.targets:
        await edit_bot_message(
            client, user_id, session.bot_message_id,
            "❌ **Please add at least one replacement target first!**"
        )
        return

    await db.update_user_state(user_id, "awaiting_replace_with")

    await edit_bot_message(
        client, user_id, session.bot_message_id,
        "✨ **Step 4/4:** Send the replacement text.\n\n"
        "Example:\n"
        "https://anizoneflix-u00w.onrender.com"
    )

@Client.on_message(filters.private & filters.text & ~filters.command([
    "start", "replace", "cancel", "done", "status"
]), group=3)
async def handle_replace_workflow(client: Client, message: Message):
    """Handle replacement workflow"""
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)

    if not session:
        message.continue_propagation()
        return

    state = await db.get_user_state(user_id)
    if not state or not state.startswith("awaiting_replace_"):
        message.continue_propagation()
        return

    try:
        await message.delete()
    except:
        pass

    if state == "awaiting_replace_first_link":
        await handle_first_link(client, message, session)
    elif state == "awaiting_replace_last_link":
        await handle_last_link(client, message, session)
    elif state == "awaiting_replace_targets":
        await handle_target(client, message, session)
    elif state == "awaiting_replace_with":
        await handle_replacement(client, message, session)

async def handle_first_link(client: Client, message: Message, session: ReplaceSession):
    """Handle first message link"""
    chat_id, msg_id, _ = parse_message_link(message.text)
    
    if not chat_id or not msg_id:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            "❌ **Invalid Link!**\n\nPlease send a valid FIRST message link."
        )
        return

    success, err_msg, chat = await verify_bot_permissions(client, chat_id)
    if not success:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            f"⚠️ **Permission Denied!**\n\n{err_msg}"
        )
        SESSIONS.pop(session.user_id, None)
        await db.reset_user(session.user_id)
        return

    if Config.REPLACE_TEXT_CHANNELS and chat.id not in Config.REPLACE_TEXT_CHANNELS:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            "❌ **Channel not authorized for replacement.**"
        )
        SESSIONS.pop(session.user_id, None)
        await db.reset_user(session.user_id)
        return

    session.chat_id = chat.id
    session.first_msg_id = msg_id
    session.chat_title = chat.title

    await db.update_user_state(session.user_id, "awaiting_replace_last_link")
    await edit_bot_message(
        client, session.user_id, session.bot_message_id,
        f"📌 **Step 2/4:** Send the **LAST** message link.\n\n"
        f"Channel: `{chat.title}`\n"
        f"First ID: `{msg_id}`"
    )

async def handle_last_link(client: Client, message: Message, session: ReplaceSession):
    """Handle last message link"""
    chat_id, msg_id, _ = parse_message_link(message.text)
    
    try:
        chat = await resolve_chat(client, chat_id)
        resolved_chat_id = chat.id
    except:
        resolved_chat_id = chat_id

    if not chat_id or not msg_id or resolved_chat_id != session.chat_id:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            f"❌ **Invalid Link!**\n\nMust be from: `{session.chat_title}`"
        )
        return

    session.last_msg_id = msg_id

    if session.first_msg_id > session.last_msg_id:
        session.first_msg_id, session.last_msg_id = session.last_msg_id, session.first_msg_id

    await db.update_user_state(session.user_id, "awaiting_replace_targets")
    
    await edit_bot_message(
        client, session.user_id, session.bot_message_id,
        f"📝 **Step 3/4:** Send everything you want to replace.\n\n"
        f"Supported:\n"
        f"• URLs\n• Words\n• Sentences\n• Emojis\n• Any text\n\n"
        f"Send unlimited targets.\n"
        f"When finished send: /done\n\n"
        f"Current targets: **{len(session.targets)}**"
    )

async def handle_target(client: Client, message: Message, session: ReplaceSession):
    """Handle replacement target"""
    item = message.text.strip()
    
    if not item:
        return
    
    if item not in session.targets:
        session.targets.append(item)
    
    display_targets = "\n".join([f"• `{t[:50]}{'...' if len(t) > 50 else ''}`" for t in session.targets[-10:]])
    
    await edit_bot_message(
        client, session.user_id, session.bot_message_id,
        f"📝 **Step 3/4:** Send targets to replace.\n\n"
        f"✅ Added: `{item}`\n\n"
        f"Current targets: **{len(session.targets)}**\n"
        f"{display_targets}\n\n"
        f"Send more targets or /done to continue."
    )

async def handle_replacement(client: Client, message: Message, session: ReplaceSession):
    """Handle replacement text and start processing"""
    session.replacement = message.text.strip()
    
    if not session.replacement:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            "❌ **Replacement text cannot be empty!**"
        )
        return

    # Start processing
    await edit_bot_message(
        client, session.user_id, session.bot_message_id,
        "🔍 **Validating...**\n"
        "📂 **Reading messages...**\n"
        "📝 **Searching captions...**\n"
        "⚡ **Starting replacement...**\n\n"
        "Please wait..."
    )

    # Create job
    job_id = f"replace_{int(time.time())}"
    job_data = {
        "job_id": job_id,
        "user_id": session.user_id,
        "chat_id": session.chat_id,
        "chat_title": session.chat_title,
        "first_id": session.first_msg_id,
        "last_id": session.last_msg_id,
        "targets": session.targets.copy(),
        "replacement": session.replacement,
        "status": "running",
        "created_at": time.time()
    }

    await db.replace_jobs.update_one(
        {"user_id": session.user_id},
        {"$set": job_data},
        upsert=True
    )

    # Clear session
    SESSIONS.pop(session.user_id, None)
    await db.reset_user(session.user_id)

    # Get bot message
    bot_msg = await client.get_messages(session.user_id, session.bot_message_id)
    if not bot_msg:
        bot_msg = await client.send_message(
            session.user_id,
            "🔄 **Starting replacement...**"
        )

    # Start task
    task = asyncio.create_task(run_replacement_task(client, job_data, bot_msg))
    ACTIVE_TASKS[session.user_id] = task

async def run_replacement_task(client: Client, job_data: Dict, status_msg: Message):
    """Run replacement task with full caption support"""
    
    user_id = job_data["user_id"]
    job_id = job_data["job_id"]
    chat_id = job_data["chat_id"]
    first_id = job_data["first_id"]
    last_id = job_data["last_id"]
    targets = job_data["targets"]
    replacement = job_data["replacement"]

    # CRITICAL: Log job parameters
    logger.info(f"🚀 Starting replace job {job_id}")
    logger.info(f"📊 Chat ID: {chat_id}")
    logger.info(f"📊 First ID: {first_id}")
    logger.info(f"📊 Last ID: {last_id}")
    logger.info(f"📊 Total messages: {last_id - first_id + 1}")
    logger.info(f"📊 Targets: {targets}")
    logger.info(f"📊 Replacement: {replacement}")

    stats = ReplacementStats()
    stats.total = last_id - first_id + 1

    # DEBUG: Test first message
    try:
        test_msg = await client.get_messages(chat_id, first_id)
        if test_msg:
            logger.info(f"✅ Successfully fetched message {first_id}")
            if test_msg.caption:
                logger.info(f"📝 Caption preview: {test_msg.caption[:200]}...")
                for target in targets:
                    if target in test_msg.caption:
                        logger.info(f"🎯 Found target '{target}' in message {first_id}")
                    else:
                        logger.warning(f"❌ Target '{target}' NOT found in message {first_id}")
            else:
                logger.warning(f"⚠️ Message {first_id} has NO caption")
        else:
            logger.error(f"❌ Failed to fetch message {first_id}")
    except Exception as e:
        logger.error(f"❌ Error fetching test message: {e}")

    # Progress update
    last_update_time = 0
    
    async def update_progress(force: bool = False):
        nonlocal last_update_time
        now = time.time()
        
        if not force and (now - last_update_time) < 3.0:
            return
        
        elapsed = int(now - stats.start_time)
        progress_bar = stats.get_progress_bar()
        percentage = stats.get_percentage()
        speed = stats.get_speed()
        speed_str = f"{int(speed)} msg/sec" if speed > 0 else "0 msg/sec"
        eta = stats.get_eta()

        progress_text = (
            "🔄 **Caption Replacement**\n\n"
            f"{progress_bar} **{percentage}%**\n\n"
            f"📂 Total: **{stats.total:,}**\n"
            f"✅ Edited: **{stats.edited:,}**\n"
            f"⏩ No Caption: **{stats.skipped_no_caption:,}**\n"
            f"⏩ No Target: **{stats.skipped_no_target:,}**\n"
            f"⏩ Unchanged: **{stats.skipped_unchanged:,}**\n"
            f"❌ Failed: **{stats.failed:,}**\n"
            f"⚡ Speed: **{speed_str}**\n"
            f"⏰ ETA: **{eta}**\n\n"
            f"📊 **{stats.processed:,}** / **{stats.total:,}** processed"
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
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

    # First progress update
    await update_progress(force=True)

    # Process messages
    for msg_id in range(first_id, last_id + 1):
        try:
            # Check cancellation
            job = await db.replace_jobs.find_one({"user_id": user_id, "job_id": job_id})
            if not job or job.get("status") == "cancelled":
                logger.info(f"Task cancelled for user {user_id}")
                await update_completion_status(client, status_msg, stats, "cancelled")
                ACTIVE_TASKS.pop(user_id, None)
                return

            # Get message
            try:
                msg = await client.get_messages(chat_id, msg_id)
                if not msg or msg.empty:
                    stats.skipped_no_caption += 1
                    stats.processed += 1
                    logger.debug(f"Message {msg_id}: Empty or None")
                    await update_progress()
                    continue
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
                msg = await client.get_messages(chat_id, msg_id)
            except Exception as e:
                stats.failed += 1
                stats.processed += 1
                stats.error_reasons[msg_id] = str(e)
                logger.error(f"Failed to fetch message {msg_id}: {e}")
                await update_progress()
                continue

            # CRITICAL: Get CAPTION (not text)
            caption = msg.caption if hasattr(msg, 'caption') and msg.caption else None
            
            if not caption:
                stats.skipped_no_caption += 1
                stats.processed += 1
                logger.debug(f"Message {msg_id}: No caption")
                await update_progress()
                continue

            # Log caption for debugging (first 5 messages only)
            if stats.processed < 5:
                logger.info(f"=== Message {msg_id} ===")
                logger.info(f"Caption: {caption[:200]}...")
                logger.info(f"Targets to check: {targets}")

            # CHECK FOR TARGETS IN CAPTION
            has_target = False
            matched_targets = []
            caption_lower = caption.lower()
            
            for target in targets:
                target_lower = target.lower()
                
                # Direct check
                if target_lower in caption_lower:
                    has_target = True
                    matched_targets.append(target)
                    logger.info(f"✅ Found target '{target}' in message {msg_id}")
                    continue
                
                # Check if target is a URL that exists in caption
                if target.startswith(('http://', 'https://')):
                    # Extract all URLs from caption
                    urls = extract_urls_from_text(caption)
                    for url, _, _ in urls:
                        url_normalized = normalize_url(url)
                        target_normalized = normalize_url(target)
                        if target_normalized in url_normalized or url_normalized in target_normalized:
                            has_target = True
                            matched_targets.append(target)
                            logger.info(f"✅ Found URL target '{target}' in message {msg_id}")
                            break
                if has_target:
                    break

            if not has_target:
                stats.skipped_no_target += 1
                stats.processed += 1
                logger.debug(f"Message {msg_id}: No target found")
                await update_progress()
                continue

            # PERFORM REPLACEMENTS
            new_caption = caption
            
            # First, replace URLs
            new_caption, url_replacements = replace_urls_in_text(new_caption, targets, replacement)
            
            # Then do direct replacements for any remaining targets
            for target in targets:
                if target in new_caption:
                    count = new_caption.count(target)
                    if count > 0:
                        new_caption = new_caption.replace(target, replacement)
                        logger.info(f"Direct replacement: {target} -> {replacement} ({count} times) in message {msg_id}")

            # Check if anything changed
            if new_caption == caption:
                stats.skipped_unchanged += 1
                stats.processed += 1
                logger.debug(f"Message {msg_id}: No changes needed")
                await update_progress()
                continue

            # EDIT CAPTION ONLY
            for attempt in range(3):
                try:
                    await client.edit_message_caption(
                        chat_id=chat_id,
                        message_id=msg.id,
                        caption=new_caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=msg.reply_markup
                    )
                    stats.edited += 1
                    stats.processed += 1
                    logger.info(f"✅ Successfully edited message {msg_id}")
                    break
                    
                except errors.FloodWait as e:
                    wait_time = e.value + 1
                    logger.warning(f"FloodWait {wait_time}s for message {msg_id}")
                    await asyncio.sleep(wait_time)
                    
                except errors.MessageNotModified:
                    stats.skipped_unchanged += 1
                    stats.processed += 1
                    logger.debug(f"Message {msg_id}: Not modified")
                    break
                    
                except errors.MessageIdInvalid:
                    stats.failed += 1
                    stats.processed += 1
                    stats.error_reasons[msg_id] = "Invalid message ID"
                    logger.error(f"Message {msg_id}: Invalid ID")
                    break
                    
                except Exception as e:
                    logger.error(f"Failed to edit message {msg_id} (attempt {attempt+1}/3): {e}")
                    if attempt == 2:
                        stats.failed += 1
                        stats.processed += 1
                        stats.error_reasons[msg_id] = str(e)
                    await asyncio.sleep(1)

            # Update progress periodically
            if stats.processed % 5 == 0:
                await update_progress()

            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info(f"Task cancelled for user {user_id}")
            await update_completion_status(client, status_msg, stats, "cancelled")
            await db.replace_jobs.update_one(
                {"user_id": user_id, "job_id": job_id},
                {"$set": {"status": "cancelled"}}
            )
            ACTIVE_TASKS.pop(user_id, None)
            return
        except Exception as e:
            logger.error(f"Unexpected error processing message {msg_id}: {e}")
            stats.failed += 1
            stats.processed += 1
            stats.error_reasons[msg_id] = str(e)

    # Completion
    stats.end_time = time.time()
    await update_progress(force=True)
    await update_completion_status(client, status_msg, stats, "completed")
    
    await db.replace_jobs.update_one(
        {"user_id": user_id, "job_id": job_id},
        {"$set": {
            "status": "completed",
            "end_time": time.time(),
            "final_stats": {
                "processed": stats.processed,
                "edited": stats.edited,
                "skipped_no_caption": stats.skipped_no_caption,
                "skipped_no_target": stats.skipped_no_target,
                "skipped_unchanged": stats.skipped_unchanged,
                "failed": stats.failed
            }
        }}
    )
    
    ACTIVE_TASKS.pop(user_id, None)
    logger.info(f"✅ Replace job {job_id} completed for user {user_id}")

async def update_completion_status(client: Client, status_msg: Message, stats: ReplacementStats, status: str):
    """Update final status"""
    elapsed = int(time.time() - stats.start_time)
    
    if status == "completed":
        title = "✅ **Replacement Completed**"
    elif status == "cancelled":
        title = "🛑 **Replacement Cancelled**"
    else:
        title = "❌ **Replacement Failed**"
    
    completion_text = (
        f"{title}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"📂 Total Messages: **{stats.total:,}**\n"
        f"✅ Captions Edited: **{stats.edited:,}**\n"
        f"⏩ No Caption: **{stats.skipped_no_caption:,}**\n"
        f"⏩ No Target Found: **{stats.skipped_no_target:,}**\n"
        f"⏩ Unchanged: **{stats.skipped_unchanged:,}**\n"
        f"❌ Failed: **{stats.failed:,}**\n"
        f"⏱️ Time: **{format_duration(elapsed)}**\n"
        f"━━━━━━━━━━━━━━"
    )
    
    if stats.error_reasons:
        completion_text += f"\n\n❌ **Errors:** {len(stats.error_reasons)} messages failed"
        error_sample = list(stats.error_reasons.items())[:5]
        for msg_id, error in error_sample:
            completion_text += f"\n• Msg {msg_id}: `{error[:50]}`"
        if len(stats.error_reasons) > 5:
            completion_text += f"\n• ... and {len(stats.error_reasons) - 5} more errors"
    
    try:
        await client.edit_message_text(
            chat_id=status_msg.chat.id,
            message_id=status_msg.id,
            text=completion_text
        )
    except Exception as e:
        logger.error(f"Failed to update completion: {e}")

@Client.on_message(filters.command("status") & filters.private & filters.user(Config.ADMINS))
async def status_command(client: Client, message: Message):
    """Check status"""
    user_id = message.from_user.id
    
    if user_id in ACTIVE_TASKS:
        job = await db.replace_jobs.find_one({"user_id": user_id, "status": "running"})
        if job:
            return await message.reply_text(
                f"📊 **Active Replace Task**\n\n"
                f"• Channel: `{job.get('chat_title')}`\n"
                f"• Job ID: `{job.get('job_id')}`\n"
                f"• Started: `{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(job.get('created_at', time.time())))}`"
            )
    
    # Check for completed jobs
    completed = await db.replace_jobs.find_one(
        {"user_id": user_id, "status": "completed"},
        sort=[("end_time", -1)]
    )
    
    if completed:
        final_stats = completed.get("final_stats", {})
        return await message.reply_text(
            f"📊 **Last Completed Task**\n\n"
            f"• Channel: `{completed.get('chat_title')}`\n"
            f"• Processed: `{final_stats.get('processed', 0):,}`\n"
            f"• Edited: `{final_stats.get('edited', 0):,}`\n"
            f"• Failed: `{final_stats.get('failed', 0):,}`\n"
            f"• Completed: `{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(completed.get('end_time', time.time())))}`"
        )
    
    await message.reply_text("ℹ️ No replace tasks found.")
