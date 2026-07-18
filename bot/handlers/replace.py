import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import deque

from pyrogram import Client, filters, errors, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.replacer import replace_in_html, replace_in_buttons, render_message_to_html
from bot.utils.stylizer import destylize
from bot.config import Config

logger = logging.getLogger(__name__)

# Registry for active asyncio tasks
ACTIVE_TASKS = {}

# Session inactivity timeout: 10 minutes (600 seconds)
SESSION_TIMEOUT = 600

# Maximum concurrent edits per batch
MAX_CONCURRENT_EDITS = 10

# Batch size for fetching messages
BATCH_SIZE = 100

@dataclass
class ReplaceSession:
    """Session data for each admin's replace operation"""
    user_id: int
    bot_message_id: int
    chat_id: Optional[int] = None
    chat_title: Optional[str] = None
    first_msg_id: Optional[int] = None
    last_msg_id: Optional[int] = None
    targets: List[str] = field(default_factory=list)
    replacement: Optional[str] = None
    step: int = 1  # 1: first link, 2: last link, 3: targets, 4: replacement
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    timeout_task: Optional[asyncio.Task] = None

class ReplacementStats:
    """Statistics for replacement job"""
    def __init__(self):
        self.total = 0
        self.processed = 0
        self.edited = 0
        self.skipped_no_caption = 0
        self.skipped_no_target = 0
        self.failed = 0
        self.start_time = time.time()
        self.end_time = None
        self.error_reasons: Dict[int, str] = {}
        self.speed_samples: deque = deque(maxlen=10)
        
    def get_speed(self) -> float:
        """Calculate current processing speed"""
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0
        return self.processed / elapsed
    
    def get_remaining(self) -> int:
        """Calculate remaining messages"""
        return max(0, self.total - self.processed)
    
    def get_eta(self) -> str:
        """Get estimated time remaining"""
        speed = self.get_speed()
        if speed == 0:
            return "--:--"
        remaining = self.get_remaining()
        eta_seconds = int(remaining / speed)
        return format_duration(eta_seconds)
    
    def get_progress_bar(self, width=15) -> str:
        """Get progress bar string"""
        if self.total == 0:
            return "░" * width
        percentage = (self.processed / self.total) * 100
        filled = int(round((percentage / 100.0) * width))
        filled = max(0, min(width, filled))
        return "█" * filled + "░" * (width - filled)
    
    def get_percentage(self) -> int:
        """Get completion percentage"""
        if self.total == 0:
            return 0
        return int((self.processed / self.total) * 100)

# Global sessions dictionary
SESSIONS: Dict[int, ReplaceSession] = {}

def format_duration(seconds: int) -> str:
    """Format duration in HH:MM:SS format"""
    if seconds < 0:
        return "--:--"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def normalize_text(text: str) -> str:
    """Normalize text for comparison while preserving original"""
    if not text:
        return text
    # Remove zero-width characters and normalize whitespace
    text = re.sub(r'[\u200b-\u200f\u2028-\u202e\u2060-\u206f\uFEFF]', '', text)
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Remove trailing spaces but keep internal structure
    lines = [line.rstrip() for line in text.split('\n')]
    return '\n'.join(lines)

def normalize_target(target: str) -> str:
    """Normalize replacement target for comparison"""
    return normalize_text(destylize(target).lower())

async def reset_session_timeout(client: Client, user_id: int):
    """Reset inactivity timeout for session"""
    if user_id not in SESSIONS:
        return
    
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

async def verify_bot_permissions(client: Client, chat_id: Any) -> Tuple[bool, str, Optional[Any]]:
    """
    Verify bot has required permissions.
    Returns: (success, message, chat_object)
    """
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

    # Bot is owner - has full permissions
    if member.status == enums.ChatMemberStatus.OWNER:
        return True, "✅ Bot is channel owner", chat

    # Bot must be administrator
    if member.status != enums.ChatMemberStatus.ADMINISTRATOR:
        return False, "❌ Bot is not an admin in this chat.", chat

    privileges = member.privileges
    if not privileges:
        return False, "❌ Bot is an admin but has no privileges.", chat

    missing = []
    
    # Check required permissions
    if is_channel:
        # For channels, need can_post_messages AND can_edit_messages
        if not getattr(privileges, "can_post_messages", False):
            missing.append("can_post_messages (required for channels)")
        if not getattr(privileges, "can_edit_messages", False):
            missing.append("can_edit_messages (required for channels)")
    else:
        # For groups, need can_manage_chat
        if not getattr(privileges, "can_manage_chat", False):
            missing.append("can_manage_chat")

    # Also check can_edit_messages for groups
    if not getattr(privileges, "can_edit_messages", False):
        missing.append("can_edit_messages")

    if missing:
        missing_str = ", ".join(f"`{p}`" for p in missing)
        return False, f"❌ Bot is admin but missing required permission(s): {missing_str}", chat

    return True, "✅ Bot has all required permissions", chat

async def edit_bot_message(client: Client, user_id: int, message_id: int, text: str):
    """Safely edit bot message with error handling"""
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=text
        )
        return True
    except errors.MessageNotModified:
        return True  # Already same text
    except Exception as e:
        logger.error(f"Failed to edit bot message: {e}")
        return False

@Client.on_message(filters.command("replace") & filters.private & filters.user(Config.ADMINS))
async def replace_command(client: Client, message: Message):
    """Start replacement workflow"""
    user_id = message.from_user.id

    # Cancel previous task if running
    if user_id in ACTIVE_TASKS:
        return await message.reply_text(
            "❌ A replacement task is already running!\n"
            "Type /cancel to stop it first."
        )

    # Clear any existing session
    if user_id in SESSIONS:
        session = SESSIONS[user_id]
        if session.timeout_task:
            session.timeout_task.cancel()
        SESSIONS.pop(user_id, None)
    
    await db.reset_user(user_id)

    # Step 1: Send first message link
    welcome_text = (
        "🛠️ **Caption Replace Tool**\n\n"
        "📌 **Step 1/4:** Send the **FIRST** Telegram message link.\n\n"
        "Example:\n"
        "https://t.me/channel/100\n\n"
        "Type /cancel anytime to exit."
    )
    
    bot_msg = await message.reply_text(welcome_text)

    # Initialize session
    session = ReplaceSession(
        user_id=user_id,
        bot_message_id=bot_msg.id
    )
    SESSIONS[user_id] = session
    await db.update_user_state(user_id, "awaiting_replace_first_link")
    await reset_session_timeout(client, user_id)

@Client.on_message(filters.command("cancel") & filters.private & filters.user(Config.ADMINS))
async def cancel_replace_command(client: Client, message: Message):
    """Cancel replacement wizard or running task"""
    user_id = message.from_user.id

    # 1. Cancel active wizard session
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

    # 2. Cancel running background task
    if user_id in ACTIVE_TASKS:
        task = ACTIVE_TASKS[user_id]
        task.cancel()
        try:
            await message.reply_text("🛑 **Replacement task is stopping...**")
        except:
            pass
        return

    await message.reply_text("ℹ️ No active replace task or wizard found.")

@Client.on_message(filters.command("done") & filters.private & filters.user(Config.ADMINS))
async def done_replace_command(client: Client, message: Message):
    """Finish adding targets and move to replacement step"""
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)
    
    if not session:
        return await message.reply_text("❌ No active replace session found.")

    state = await db.get_user_state(user_id)
    if state != "awaiting_replace_targets":
        return

    # Delete `/done` user message
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
    await reset_session_timeout(client, user_id)

    await edit_bot_message(
        client, user_id, session.bot_message_id,
        "✨ **Step 4/4:** Send the replacement text.\n\n"
        "Example:\n"
        "https://anizoneflix-u00w.onrender.com"
    )

@Client.on_message(filters.private & filters.text & ~filters.command([
    "start", "replace", "cancel", "done", "status", "resume"
]), group=3)
async def handle_replace_workflow(client: Client, message: Message):
    """Handle replacement workflow steps"""
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)

    if not session:
        message.continue_propagation()
        return

    state = await db.get_user_state(user_id)
    if not state or not state.startswith("awaiting_replace_"):
        message.continue_propagation()
        return

    # Delete user's message to keep chat clean
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete user message: {e}")

    await reset_session_timeout(client, user_id)

    if state == "awaiting_replace_first_link":
        await handle_first_link(client, message, session)
    
    elif state == "awaiting_replace_last_link":
        await handle_last_link(client, message, session)
    
    elif state == "awaiting_replace_targets":
        await handle_target(client, message, session)
    
    elif state == "awaiting_replace_with":
        await handle_replacement(client, message, session)

async def handle_first_link(client: Client, message: Message, session: ReplaceSession):
    """Handle first message link input"""
    chat_id, msg_id, _ = parse_message_link(message.text)
    
    if not chat_id or not msg_id:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            "❌ **Invalid Link!**\n\n"
            "Please send a valid FIRST message link.\n\n"
            "Example:\n"
            "https://t.me/channel/100"
        )
        return

    # Verify bot permissions
    success, err_msg, chat = await verify_bot_permissions(client, chat_id)
    if not success:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            f"⚠️ **Permission Denied!**\n\n{err_msg}\n\n"
            "Please fix permissions and start over with /replace."
        )
        SESSIONS.pop(session.user_id, None)
        await db.reset_user(session.user_id)
        return

    # Check if channel is authorized
    if Config.REPLACE_TEXT_CHANNELS and chat.id not in Config.REPLACE_TEXT_CHANNELS:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            "❌ **This channel is not authorized for text replacement.**\n\n"
            "Contact bot owner to authorize this channel."
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
        f"📌 **Step 2/4:** Send the **LAST** Telegram message link.\n\n"
        f"Channel: `{chat.title}`\n"
        f"First ID: `{msg_id}`\n\n"
        "Example:\n"
        "https://t.me/channel/500"
    )

async def handle_last_link(client: Client, message: Message, session: ReplaceSession):
    """Handle last message link input"""
    chat_id, msg_id, _ = parse_message_link(message.text)
    
    # Resolve chat ID to compare
    try:
        chat = await resolve_chat(client, chat_id)
        resolved_chat_id = chat.id
    except:
        resolved_chat_id = chat_id

    if not chat_id or not msg_id or resolved_chat_id != session.chat_id:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            f"❌ **Invalid Link!**\n\n"
            f"Link must be from the same channel: `{session.chat_title}`\n\n"
            f"📩 Send the LAST message link."
        )
        return

    session.last_msg_id = msg_id

    # Ensure correct order
    if session.first_msg_id > session.last_msg_id:
        session.first_msg_id, session.last_msg_id = session.last_msg_id, session.first_msg_id

    await db.update_user_state(session.user_id, "awaiting_replace_targets")
    
    target_list = "\n".join([f"• {t}" for t in session.targets[-5:]]) if session.targets else "No targets added yet"
    target_count = len(session.targets)
    
    await edit_bot_message(
        client, session.user_id, session.bot_message_id,
        f"📝 **Step 3/4:** Send everything you want to replace.\n\n"
        f"Supported:\n"
        f"• URLs\n"
        f"• Words\n"
        f"• Sentences\n"
        f"• Emojis\n"
        f"• HTML\n"
        f"• Markdown\n"
        f"• Any text\n\n"
        f"You can send unlimited targets.\n\n"
        f"Current targets: {target_count}\n"
        f"{target_list if target_count > 0 else 'No targets added yet'}\n\n"
        f"Continue sending targets.\n"
        f"When finished send: /done"
    )

async def handle_target(client: Client, message: Message, session: ReplaceSession):
    """Handle replacement target input"""
    item = message.text.strip()
    
    if not item:
        return
    
    # Check for duplicates
    if item not in session.targets:
        session.targets.append(item)
    
    target_list = "\n".join([f"• {t}" for t in session.targets[-10:]])
    target_count = len(session.targets)
    
    await edit_bot_message(
        client, session.user_id, session.bot_message_id,
        f"📝 **Step 3/4:** Send everything you want to replace.\n\n"
        f"✅ Added: `{item}`\n\n"
        f"Current targets: {target_count}\n"
        f"{target_list}\n\n"
        f"Continue sending targets.\n"
        f"When finished send: /done"
    )

async def handle_replacement(client: Client, message: Message, session: ReplaceSession):
    """Handle replacement text and start processing"""
    session.replacement = message.text.strip()
    
    if not session.replacement:
        await edit_bot_message(
            client, session.user_id, session.bot_message_id,
            "❌ **Replacement text cannot be empty!**\n\n"
            "Please send the replacement text."
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

    # Create job data
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

    # Save to database
    await db.replace_jobs.update_one(
        {"user_id": session.user_id},
        {"$set": job_data},
        upsert=True
    )

    # Clear session
    if session.timeout_task:
        session.timeout_task.cancel()
    SESSIONS.pop(session.user_id, None)
    await db.reset_user(session.user_id)

    # Get bot message for updates
    bot_msg = await client.get_messages(session.user_id, session.bot_message_id)
    if not bot_msg:
        # Create new status message if original was deleted
        bot_msg = await client.send_message(
            session.user_id,
            "🔄 **Starting replacement...**"
        )

    # Start replacement task
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

    stats = ReplacementStats()
    stats.total = last_id - first_id + 1
    stats.start_time = time.time()

    # Normalize targets for efficient matching
    normalized_targets = [(target, normalize_target(target)) for target in targets]
    normalized_replacement = normalize_target(replacement)

    # Progress update interval
    last_update_time = 0
    update_interval = 3.0  # seconds

    # Ensure status_msg exists
    if not status_msg:
        try:
            status_msg = await client.send_message(
                user_id,
                "🔄 **Starting replacement...**"
            )
        except:
            logger.error(f"Failed to send status message for user {user_id}")
            return

    async def update_progress(force: bool = False):
        """Update progress message"""
        nonlocal last_update_time
        now = time.time()
        
        if not force and (now - last_update_time) < update_interval:
            return
        
        elapsed = int(now - stats.start_time)
        progress_bar = stats.get_progress_bar()
        percentage = stats.get_percentage()
        speed = stats.get_speed()
        speed_str = f"{int(speed)} msg/sec" if speed > 0 else "0 msg/sec"
        remaining = stats.get_remaining()
        eta = stats.get_eta()

        progress_text = (
            "🔄 **Caption Replacement**\n\n"
            f"{progress_bar} **{percentage}%**\n\n"
            f"📂 Total: **{stats.total}**\n"
            f"✅ Edited: **{stats.edited}**\n"
            f"⏩ Skipped (No Caption): **{stats.skipped_no_caption}**\n"
            f"⏩ Skipped (No Target): **{stats.skipped_no_target}**\n"
            f"❌ Failed: **{stats.failed}**\n"
            f"⚡ Speed: **{speed_str}**\n"
            f"⏳ Remaining: **{remaining}**\n"
            f"⏰ ETA: **{eta}**\n\n"
            f"🔍 Processed: **{stats.processed}/{stats.total}**"
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

    # Process messages in batches
    for batch_start in range(first_id, last_id + 1, BATCH_SIZE):
        # Check for cancellation
        job = await db.replace_jobs.find_one({"user_id": user_id, "job_id": job_id})
        if not job or job.get("status") == "cancelled":
            logger.info(f"Replace task {job_id} cancelled")
            await update_completion_status(client, status_msg, stats, "cancelled")
            return

        batch_end = min(batch_start + BATCH_SIZE - 1, last_id)
        batch_ids = list(range(batch_start, batch_end + 1))

        try:
            messages = await client.get_messages(chat_id, batch_ids)
        except errors.FloodWait as e:
            logger.warning(f"Flood wait {e.value}s for batch {batch_start}")
            await asyncio.sleep(e.value + 1)
            messages = await client.get_messages(chat_id, batch_ids)
        except Exception as e:
            logger.error(f"Failed to fetch batch {batch_start}: {e}")
            stats.failed += len(batch_ids)
            stats.processed += len(batch_ids)
            continue

        if not isinstance(messages, list):
            messages = [messages]

        # Process messages with semaphore for concurrency control
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EDITS)
        
        async def process_message(msg):
            if not msg or msg.empty:
                stats.skipped_no_caption += 1
                return

            # Get caption (NOT text)
            caption = msg.caption if hasattr(msg, 'caption') and msg.caption else None
            
            if not caption:
                stats.skipped_no_caption += 1
                return

            # Check for targets (use normalized comparison)
            has_match = False
            caption_normalized = normalize_text(caption)
            
            for target, target_normalized in normalized_targets:
                if target_normalized in caption_normalized:
                    has_match = True
                    break
                
                # Also check in caption entities (URLs, etc.)
                if msg.caption_entities:
                    for entity in msg.caption_entities:
                        if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                            entity_text = caption[entity.offset:entity.offset + entity.length]
                            if target_normalized in normalize_text(entity_text):
                                has_match = True
                                break
                    if has_match:
                        break

            if not has_match:
                stats.skipped_no_target += 1
                return

            # Perform replacement on the full caption
            new_caption = caption
            for target, _ in normalized_targets:
                if target in new_caption:
                    new_caption = new_caption.replace(target, replacement)
            
            # Also handle entity-based replacement (URLs with text links)
            # This ensures URLs are replaced even when they're in entities
            if msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                        entity_text = caption[entity.offset:entity.offset + entity.length]
                        for target, target_normalized in normalized_targets:
                            if target_normalized in normalize_text(entity_text):
                                # Replace in the entity text
                                new_text = entity_text.replace(target, replacement)
                                # Update the caption
                                new_caption = new_caption[:entity.offset] + new_text + new_caption[entity.offset + entity.length:]
                                break

            # Only edit if caption actually changed
            if new_caption == caption:
                stats.skipped_no_target += 1
                return

            # Edit caption (NOT text)
            async with semaphore:
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
                        break
                    except errors.FloodWait as e:
                        wait_time = e.value + 1
                        logger.warning(f"Flood wait {wait_time}s for message {msg.id}")
                        await asyncio.sleep(wait_time)
                    except errors.MessageNotModified:
                        stats.skipped_no_target += 1
                        break
                    except errors.MessageIdInvalid:
                        logger.warning(f"Invalid message ID: {msg.id}")
                        stats.failed += 1
                        break
                    except Exception as e:
                        logger.error(f"Failed to edit message {msg.id} (attempt {attempt}): {e}")
                        if attempt == 2:
                            stats.failed += 1
                            stats.error_reasons[msg.id] = str(e)
                        await asyncio.sleep(1)

        # Process batch with semaphore
        await asyncio.gather(*[process_message(msg) for msg in messages])
        stats.processed += len(messages)

        # Update progress
        await update_progress()

        # Save progress to database
        await db.replace_jobs.update_one(
            {"user_id": user_id, "job_id": job_id},
            {"$set": {
                "processed": stats.processed,
                "edited": stats.edited,
                "skipped_no_caption": stats.skipped_no_caption,
                "skipped_no_target": stats.skipped_no_target,
                "failed": stats.failed,
                "last_updated": time.time()
            }}
        )

        # Small delay between batches to avoid rate limits
        await asyncio.sleep(0.5)

    # Completion
    stats.end_time = time.time()
    await update_progress(force=True)
    await update_completion_status(client, status_msg, stats, "completed")
    
    # Update database
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
                "failed": stats.failed
            }
        }}
    )
    
    ACTIVE_TASKS.pop(user_id, None)
    logger.info(f"Replace job {job_id} completed for user {user_id}")

async def update_completion_status(client: Client, status_msg: Message, stats: ReplacementStats, status: str):
    """Update final completion status message"""
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
        f"📂 Total Messages: **{stats.total}**\n"
        f"✅ Captions Edited: **{stats.edited}**\n"
        f"⏩ Skipped (No Caption): **{stats.skipped_no_caption}**\n"
        f"⏩ Skipped (No Target): **{stats.skipped_no_target}**\n"
        f"❌ Failed: **{stats.failed}**\n"
        f"⏱️ Elapsed Time: **{format_duration(elapsed)}**\n"
        f"━━━━━━━━━━━━━━"
    )
    
    if stats.error_reasons:
        error_summary = "\n\n❌ **Errors:**\n"
        for msg_id, error in list(stats.error_reasons.items())[:5]:
            error_summary += f"• Message {msg_id}: `{error}`\n"
        if len(stats.error_reasons) > 5:
            error_summary += f"• ... and {len(stats.error_reasons) - 5} more errors"
        completion_text += error_summary
    
    try:
        await client.edit_message_text(
            chat_id=status_msg.chat.id,
            message_id=status_msg.id,
            text=completion_text
        )
    except Exception as e:
        logger.error(f"Failed to update completion message: {e}")

@Client.on_message(filters.command("status") & filters.private & filters.user(Config.ADMINS))
async def status_replace_command(client: Client, message: Message):
    """Check status of running replacement task"""
    user_id = message.from_user.id
    
    # Check memory first
    if user_id in ACTIVE_TASKS:
        job = await db.replace_jobs.find_one({"user_id": user_id, "status": "running"})
        if job:
            stats = job.get("stats", {})
            return await message.reply_text(
                f"📊 **Active Replace Task**\n\n"
                f"• Channel: `{job.get('chat_title')}`\n"
                f"• Processed: `{stats.get('processed', 0)}`\n"
                f"• Edited: `{stats.get('edited', 0)}`\n"
                f"• Failed: `{stats.get('failed', 0)}`"
            )
    
    # Check database
    job = await db.replace_jobs.find_one({"user_id": user_id, "status": "running"})
    if job:
        stats = job.get("stats", {})
        return await message.reply_text(
            f"📊 **Active Replace Task**\n\n"
            f"• Channel: `{job.get('chat_title')}`\n"
            f"• Processed: `{stats.get('processed', 0)}`\n"
            f"• Edited: `{stats.get('edited', 0)}`\n"
            f"• Failed: `{stats.get('failed', 0)}`"
        )
    
    # Check for completed jobs
    completed = await db.replace_jobs.find_one(
        {"user_id": user_id, "status": "completed"},
        sort=[("end_time", -1)]
    )
    
    if completed:
        stats = completed.get("final_stats", {})
        return await message.reply_text(
            f"📊 **Last Completed Task**\n\n"
            f"• Channel: `{completed.get('chat_title')}`\n"
            f"• Processed: `{stats.get('processed', 0)}`\n"
            f"• Edited: `{stats.get('edited', 0)}`\n"
            f"• Failed: `{stats.get('failed', 0)}`"
        )
    
    await message.reply_text("ℹ️ No replace tasks found.")

@Client.on_message(filters.command("resume") & filters.private & filters.user(Config.ADMINS))
async def resume_replace_command(client: Client, message: Message):
    """Resume a paused or failed replacement task"""
    user_id = message.from_user.id
    
    if user_id in ACTIVE_TASKS:
        return await message.reply_text("❌ A replacement task is already running!")

    job = await db.replace_jobs.find_one({
        "user_id": user_id,
        "status": {"$in": ["paused", "failed"]}
    })

    if not job:
        return await message.reply_text("❌ No unfinished replace tasks found to resume.")

    # Check if job can be resumed
    first_id = job.get("first_id")
    last_id = job.get("last_id")
    current_id = job.get("current_id", first_id)
    
    if current_id > last_id:
        return await message.reply_text("⚠️ Job appears to be already complete.")

    # Create status message
    status_msg = await message.reply_text("🔄 **Resuming replacement task...**")

    # Update status
    await db.replace_jobs.update_one(
        {"user_id": user_id, "job_id": job["job_id"]},
        {"$set": {"status": "running"}}
    )
    
    job["status"] = "running"
    job["current_id"] = current_id

    # Start task
    task = asyncio.create_task(run_replacement_task(client, job, status_msg))
    ACTIVE_TASKS[user_id] = task
    
    logger.info(f"Resumed replace job {job['job_id']} for user {user_id}")
