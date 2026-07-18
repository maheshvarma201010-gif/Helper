import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
import html

from pyrogram import Client, filters, errors, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.replacer import replace_in_html, replace_in_buttons, render_message_to_html
from bot.utils.stylizer import destylize
from bot.config import Config

logger = logging.getLogger(__name__)

# Active tasks registry
ACTIVE_TASKS = {}

# Sessions registry
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
    last_activity: float = field(default_factory=time.time)

class ReplacementStats:
    """Comprehensive statistics tracking"""
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
        self.processed_messages: Set[int] = set()
        self.found_targets: Dict[str, int] = {}
        self.replacement_count: Dict[str, int] = {}
        
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

def normalize_text(text: str) -> str:
    """Normalize text for comparison"""
    if not text:
        return text
    # Remove zero-width and invisible characters
    text = re.sub(r'[\u200b-\u200f\u2028-\u202e\u2060-\u206f\uFEFF]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_all_urls(text: str) -> List[str]:
    """Extract all URLs from text including markdown links"""
    urls = []
    
    # Standard URL pattern
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls.extend(re.findall(url_pattern, text))
    
    # Markdown links
    markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    for match in re.finditer(markdown_pattern, text):
        url = match.group(2)
        if url.startswith('http'):
            urls.append(url)
    
    return urls

async def verify_bot_permissions(client: Client, chat_id: Any) -> Tuple[bool, str, Optional[Any]]:
    """Verify bot has required permissions"""
    try:
        chat = await resolve_chat(client, chat_id)
    except Exception as e:
        return False, f"❌ Failed to resolve chat: {e}", None

    is_channel = chat.type == enums.ChatType.CHANNEL
    
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
        return False, "❌ Bot is an admin but has no privileges.", chat

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
        missing_str = ", ".join(f"`{p}`" for p in missing)
        return False, f"❌ Missing permissions: {missing_str}", chat

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
        except Exception as e:
            logger.warning(f"Failed to edit cancel message: {e}")
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
            "❌ **Please add at least one replacement target first!**\n\n"
            "Send text, URLs, emojis, or any string to replace."
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
            f"⚠️ **Permission Denied!**\n\n{err_msg}\n\nPlease fix permissions."
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
    
    # Show last 10 targets
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
    """Run replacement with unlimited processing"""
    
    user_id = job_data["user_id"]
    job_id = job_data["job_id"]
    chat_id = job_data["chat_id"]
    first_id = job_data["first_id"]
    last_id = job_data["last_id"]
    targets = job_data["targets"]
    replacement = job_data["replacement"]

    stats = ReplacementStats()
    stats.total = last_id - first_id + 1

    # Sort targets by length (longest first) for proper replacement
    targets_sorted = sorted(targets, key=len, reverse=True)

    # Progress update function
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
            f"📂 Total: **{stats.total}**\n"
            f"✅ Edited: **{stats.edited}**\n"
            f"⏩ No Caption: **{stats.skipped_no_caption}**\n"
            f"⏩ No Target: **{stats.skipped_no_target}**\n"
            f"⏩ Unchanged: **{stats.skipped_unchanged}**\n"
            f"❌ Failed: **{stats.failed}**\n"
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

    # Process messages WITHOUT batch limits
    message_cache = {}
    
    async def process_single_message(msg_id: int):
        """Process a single message"""
        
        # Check cancellation
        job = await db.replace_jobs.find_one({"user_id": user_id, "job_id": job_id})
        if not job or job.get("status") == "cancelled":
            return False

        # Get message from cache or fetch
        if msg_id in message_cache:
            msg = message_cache[msg_id]
        else:
            try:
                msg = await client.get_messages(chat_id, msg_id)
                message_cache[msg_id] = msg
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    msg = await client.get_messages(chat_id, msg_id)
                    message_cache[msg_id] = msg
                except Exception as e:
                    stats.failed += 1
                    stats.error_reasons[msg_id] = str(e)
                    return True
            except Exception as e:
                stats.failed += 1
                stats.error_reasons[msg_id] = str(e)
                return True

        if not msg or msg.empty:
            stats.skipped_no_caption += 1
            return True

        # CRITICAL: Get CAPTION not text
        caption = msg.caption if hasattr(msg, 'caption') and msg.caption else None
        
        if not caption:
            stats.skipped_no_caption += 1
            return True

        # Check for targets in FULL caption
        has_match = False
        matched_targets = []
        caption_lower = caption.lower()
        
        for target in targets_sorted:
            target_lower = target.lower()
            
            # Direct match in entire caption
            if target_lower in caption_lower:
                has_match = True
                matched_targets.append(target)
                stats.found_targets[target] = stats.found_targets.get(target, 0) + 1
                continue
            
            # Check in markdown links
            markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
            for match in re.finditer(markdown_pattern, caption):
                link_url = match.group(2)
                link_text = match.group(1)
                if target_lower in link_url.lower() or target_lower in link_text.lower():
                    has_match = True
                    matched_targets.append(target)
                    stats.found_targets[target] = stats.found_targets.get(target, 0) + 1
                    break
            
            # Check in URLs
            if not has_match:
                urls = extract_all_urls(caption)
                for url in urls:
                    if target_lower in url.lower():
                        has_match = True
                        matched_targets.append(target)
                        stats.found_targets[target] = stats.found_targets.get(target, 0) + 1
                        break

        if not has_match:
            stats.skipped_no_target += 1
            return True

        # Perform replacements on FULL caption
        new_caption = caption
        replacements_made = 0
        
        for target in matched_targets:
            if target in new_caption:
                count = new_caption.count(target)
                new_caption = new_caption.replace(target, replacement)
                replacements_made += count
                stats.replacement_count[target] = stats.replacement_count.get(target, 0) + count
        
        # Also handle markdown links specifically
        def replace_markdown(match):
            link_text = match.group(1)
            link_url = match.group(2)
            for target in matched_targets:
                if target in link_url:
                    link_url = link_url.replace(target, replacement)
                if target in link_text:
                    link_text = link_text.replace(target, replacement)
            return f'[{link_text}]({link_url})'
        
        new_caption = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_markdown, new_caption)

        # Skip if no changes
        if new_caption == caption:
            stats.skipped_unchanged += 1
            return True

        # Edit CAPTION only
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
                logger.info(f"✅ Edited message {msg.id} ({replacements_made} replacements)")
                break
            except errors.FloodWait as e:
                wait_time = e.value + 1
                logger.warning(f"FloodWait {wait_time}s for message {msg.id}")
                await asyncio.sleep(wait_time)
            except errors.MessageNotModified:
                stats.skipped_unchanged += 1
                break
            except errors.MessageIdInvalid:
                stats.failed += 1
                stats.error_reasons[msg.id] = "Invalid message ID"
                break
            except Exception as e:
                logger.error(f"Failed to edit message {msg.id} (attempt {attempt+1}/3): {e}")
                if attempt == 2:
                    stats.failed += 1
                    stats.error_reasons[msg.id] = str(e)
                await asyncio.sleep(1)

        return True

    # First progress update
    await update_progress(force=True)

    # Process ALL messages WITHOUT batch limits
    # Create tasks for all messages
    logger.info(f"Starting processing {stats.total} messages for user {user_id}")
    
    for msg_id in range(first_id, last_id + 1):
        try:
            await process_single_message(msg_id)
            stats.processed += 1
            
            # Update progress periodically
            if stats.processed % 10 == 0:
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
    logger.info(f"✅ Replace job {job_id} completed")

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
    
    # Add target statistics
    if stats.found_targets:
        completion_text += "\n\n📊 **Targets Found:**\n"
        for target, count in sorted(stats.found_targets.items(), key=lambda x: x[1], reverse=True)[:10]:
            completion_text += f"• `{target[:30]}`: {count} times\n"
    
    if stats.replacement_count:
        completion_text += "\n🔄 **Replacements Made:**\n"
        for target, count in sorted(stats.replacement_count.items(), key=lambda x: x[1], reverse=True)[:10]:
            completion_text += f"• `{target[:30]}`: {count} replacements\n"
    
    if stats.error_reasons:
        completion_text += f"\n❌ **Errors:** {len(stats.error_reasons)} messages failed"
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
            stats = job.get("stats", {})
            return await message.reply_text(
                f"📊 **Active Replace Task**\n\n"
                f"• Channel: `{job.get('chat_title')}`\n"
                f"• Processed: `{stats.get('processed', 0):,}`\n"
                f"• Edited: `{stats.get('edited', 0):,}`\n"
                f"• Failed: `{stats.get('failed', 0):,}`"
            )
    
    await message.reply_text("ℹ️ No active replace tasks found.")
