import asyncio
import logging
import uuid
import time
from pyrogram import Client, filters, errors, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument
from bot.database.mongo import db
from bot.config import Config
from bot.utils.helpers import parse_message_link, resolve_chat

logger = logging.getLogger(__name__)

# Dictionary to keep track of active tasks in memory
active_prof_tasks = {}

@Client.on_message(filters.command("forward") & filters.user(Config.ADMINS) & filters.private, group=-2)
async def prof_forward_command(client, message):
    # Check if admin userbot is active
    if not hasattr(client, "admin_userbot") or not client.admin_userbot:
        if await db.get_admin_session():
            # Try to initialize but don't block standard handler yet if it fails
            await client.init_admin_userbot()
            if not client.admin_userbot:
                 return # Let it fall through to standard handler
        else:
            # Not logged in to professional system, let standard handler take over
            return

    # If we are here, we are logged in and want to use professional system
    message.stop_propagation()
    user_id = message.from_user.id
    await db.reset_user(user_id)

    await db.update_user_state(user_id, "prof_fwd_awaiting_start")
    await message.reply_text(
        "🚀 **Professional Forwarding**\n\n"
        "Please send the **First Message Link**."
    )

@Client.on_message(filters.command("forwardstop") & filters.user(Config.ADMINS) & filters.private, group=-2)
async def prof_forwardstop_command(client, message):
    message.stop_propagation()
    user_id = message.from_user.id
    active_jobs = await db.prof_forward_jobs.find({"user_id": user_id, "status": "running"}).to_list(length=None)

    if not active_jobs:
        return await message.reply_text("❌ No active professional forwarding jobs.")

    for job in active_jobs:
        job_id = job["job_id"]
        await db.update_prof_forward_job(job_id, {"status": "stopped"})
        if job_id in active_prof_tasks:
            active_prof_tasks[job_id].cancel()

    await message.reply_text(f"🛑 Stopped {len(active_jobs)} professional job(s).")

@Client.on_message(filters.private & filters.user(Config.ADMINS), group=-2)
async def handle_prof_fwd_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)
    if not state or not state.startswith("prof_fwd_"):
        return

    text = message.text.strip() if message.text else None
    if not text:
        return

    message.stop_propagation()

    if text == "/cancel":
        await db.reset_user(user_id)
        return await message.reply_text("✅ Operation cancelled.")

    user_data = await db.get_user(user_id)
    prof_data = user_data.get("prof_fwd_data", {})

    if state == "prof_fwd_awaiting_start":
        chat_id, first_id, _ = parse_message_link(text)
        if not chat_id:
            return await message.reply_text("❌ Invalid link. Please send a valid Telegram message link.")

        prof_data["source_chat"] = chat_id
        prof_data["start_id"] = first_id
        prof_data["source_link"] = text

        await db.users.update_one({"user_id": user_id}, {"$set": {"prof_fwd_data": prof_data}})
        await db.update_user_state(user_id, "prof_fwd_awaiting_end")
        await message.reply_text("✅ Start link saved.\n\nNow send the **Last Message Link**.")

    elif state == "prof_fwd_awaiting_end":
        chat_id, last_id, _ = parse_message_link(text)
        if not chat_id or chat_id != prof_data.get("source_chat"):
            return await message.reply_text("❌ Link must be from the same channel as the start link.")

        prof_data["end_id"] = last_id
        await db.users.update_one({"user_id": user_id}, {"$set": {"prof_fwd_data": prof_data}})
        await db.update_user_state(user_id, "prof_fwd_awaiting_target")
        await message.reply_text("✅ End link saved.\n\nNow send the **Target Channel ID/Username/Link**.")

    elif state == "prof_fwd_awaiting_target":
        try:
            # Verification Step
            target_chat = await resolve_chat(client.admin_userbot, text)

            # Send hidden verification message
            try:
                v_msg = await client.admin_userbot.send_message(target_chat.id, "Checking permissions...")
                await v_msg.delete()
            except Exception as e:
                return await message.reply_text(f"❌ Cannot send messages to target: {e}")

            prof_data["target_chat"] = target_chat.id
            prof_data["target_title"] = target_chat.title
            # Default filters: all selected
            prof_data["filters"] = ["files", "videos", "photos", "audio", "voice", "animations", "video_notes", "stickers", "text", "links", "polls", "locations", "contacts", "documents", "albums"]

            await db.users.update_one({"user_id": user_id}, {"$set": {"prof_fwd_data": prof_data}})
            await db.update_user_state(user_id, "prof_fwd_awaiting_filters")

            await message.reply_text(
                "📂 **Select what you want to forward**\n\nYou can select one or multiple message types, then press ✅ Done to start forwarding.",
                reply_markup=get_filter_markup(prof_data["filters"])
            )

        except Exception as e:
            logger.error(f"Target resolution error: {e}")
            return await message.reply_text(f"❌ Could not resolve target or insufficient permissions: {e}")

FILTER_TYPES = {
    "files": "📁 Files", "videos": "🎥 Videos", "photos": "🖼 Photos",
    "audio": "🎵 Audio", "voice": "🎤 Voice", "animations": "🎬 Animations",
    "video_notes": "🎥 Video Notes", "stickers": "😀 Stickers", "text": "📝 Text Messages",
    "links": "🔗 Links", "polls": "📊 Polls", "locations": "📍 Locations",
    "contacts": "👤 Contacts", "documents": "📦 Documents", "albums": "📚 Albums"
}

def get_filter_markup(selected_filters):
    buttons = []
    keys = list(FILTER_TYPES.keys())
    for i in range(0, len(keys), 2):
        row = []
        for key in keys[i:i+2]:
            text = f"✅ {FILTER_TYPES[key]}" if key in selected_filters else FILTER_TYPES[key]
            row.append(InlineKeyboardButton(text, callback_data=f"prof_fwd_filter:toggle:{key}"))
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("✅ Select All", callback_data="prof_fwd_filter:all"),
        InlineKeyboardButton("❌ Clear All", callback_data="prof_fwd_filter:clear")
    ])
    buttons.append([InlineKeyboardButton("✅ Done", callback_data="prof_fwd_filter:done")])
    return InlineKeyboardMarkup(buttons)

@Client.on_callback_query(filters.regex(r"^prof_fwd_filter:(.+)"))
async def prof_fwd_filter_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data.split(":")
    action = data[1]

    user_data = await db.get_user(user_id)
    prof_data = user_data.get("prof_fwd_data", {})
    selected = prof_data.get("filters", [])

    if action == "toggle":
        key = data[2]
        if key in selected: selected.remove(key)
        else: selected.append(key)
    elif action == "all":
        selected = list(FILTER_TYPES.keys())
    elif action == "clear":
        selected = []
    elif action == "done":
        if not selected:
            return await callback_query.answer("⚠ Please select at least one message type.", show_alert=True)

        await callback_query.answer("Starting...")

        job_id = str(uuid.uuid4())[:8]
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "source_chat": prof_data["source_chat"],
            "start_id": min(prof_data["start_id"], prof_data["end_id"]),
            "end_id": max(prof_data["start_id"], prof_data["end_id"]),
            "target_chat": prof_data["target_chat"],
            "target_title": prof_data["target_title"],
            "filters": selected,
            "current_id": min(prof_data["start_id"], prof_data["end_id"]),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total": abs(prof_data["end_id"] - prof_data["start_id"]) + 1,
            "status": "running",
            "start_time": time.time()
        }

        await db.add_prof_forward_job(job_data)
        await db.reset_user(user_id)

        status_msg = await callback_query.message.edit_text("⏳ Starting professional forward...")
        task = asyncio.create_task(prof_forward_worker(client, job_id, status_msg))
        active_prof_tasks[job_id] = task
        return

    prof_data["filters"] = selected
    await db.users.update_one({"user_id": user_id}, {"$set": {"prof_fwd_data": prof_data}})

    try:
        await callback_query.message.edit_reply_markup(get_filter_markup(selected))
    except: pass

def get_progress_bar(percentage):
    c = int(percentage / 10)
    return "█" * c + "░" * (10 - c)

async def init_prof_worker(client):
    """Resume active professional forwarding jobs on startup."""
    active_jobs = await db.get_all_active_prof_forward_jobs()
    for job in active_jobs:
        job_id = job["job_id"]
        # We don't have a status_msg on resume, but we can send one to admin
        if Config.OWNER_ID:
            try:
                status_msg = await client.send_message(Config.OWNER_ID, f"🔄 Resuming professional job `{job_id}`...")
                task = asyncio.create_task(prof_forward_worker(client, job_id, status_msg))
                active_prof_tasks[job_id] = task
            except: pass

def is_allowed_type(msg, filters):
    if not msg: return False

    # Photos
    if "photos" in filters and msg.photo: return True

    # Videos
    if "videos" in filters and msg.video: return True

    # Files / Documents
    if "files" in filters and msg.document: return True
    if "documents" in filters and msg.document: return True

    # Audio / Voice
    if "audio" in filters and msg.audio: return True
    if "voice" in filters and msg.voice: return True

    # Animations / GIF
    if "animations" in filters and msg.animation: return True

    # Video Notes
    if "video_notes" in filters and msg.video_note: return True

    # Stickers
    if "stickers" in filters and msg.sticker: return True

    # Polls
    if "polls" in filters and msg.poll: return True

    # Locations
    if "locations" in filters and msg.location: return True

    # Contacts
    if "contacts" in filters and msg.contact: return True

    # Albums
    if "albums" in filters and msg.media_group_id: return True

    # Text Messages (Strictly plain text)
    if "text" in filters and msg.text and not msg.entities:
        # Check if it has URLs - if so, it might belong to 'links'
        return True

    # Links (Contains URLs or Text Links)
    if "links" in filters:
        entities = msg.entities or msg.caption_entities
        if entities:
            for entity in entities:
                if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                    return True

    # Broad 'text' check
    if "text" in filters and msg.text: return True

    return False

async def prof_forward_worker(client, job_id, status_msg):
    try:
        job = await db.get_prof_forward_job(job_id)
        if not job: return

        while not hasattr(client, "admin_userbot") or not client.admin_userbot:
            await asyncio.sleep(5)

        userbot = client.admin_userbot
        source = job["source_chat"]
        target = job["target_chat"]
        filters_list = job.get("filters", [])

        last_update = 0
        processed_media_groups = set()

        curr_id = job["current_id"]

        # Batch size for get_messages to increase speed
        BATCH_SIZE = 20

        while curr_id <= job["end_id"]:
            # Check if job was stopped
            job = await db.get_prof_forward_job(job_id)
            if not job or job["status"] != "running":
                break

            try:
                # Fetch a batch of messages
                batch_ids = list(range(curr_id, min(curr_id + BATCH_SIZE, job["end_id"] + 1)))
                messages = await userbot.get_messages(source, batch_ids)

                if not isinstance(messages, list):
                    messages = [messages]

                for msg in messages:
                    # Refresh job status in inner loop to allow stopping mid-batch
                    job = await db.get_prof_forward_job(job_id)
                    if not job or job["status"] != "running":
                         break

                    if not msg or msg.empty:
                        job["skipped"] += 1
                    elif not is_allowed_type(msg, filters_list):
                        job["skipped"] += 1
                    else:
                        if msg.media_group_id:
                            if msg.media_group_id in processed_media_groups:
                                job["skipped"] += 1
                            else:
                                try:
                                    # Fetch full media group
                                    group_msgs = await userbot.get_media_group(source, msg.id)
                                    # Copy the whole group (Pyrogram doesn't have copy_media_group, use custom logic or copy one by one)
                                    # Correct way to 're-send' a media group as if new:
                                    media = []
                                    for m in group_msgs:
                                        if m.photo: media.append(InputMediaPhoto(m.photo.file_id, caption=m.caption, caption_entities=m.caption_entities))
                                        elif m.video: media.append(InputMediaVideo(m.video.file_id, caption=m.caption, caption_entities=m.caption_entities))
                                        elif m.audio: media.append(InputMediaAudio(m.audio.file_id, caption=m.caption, caption_entities=m.caption_entities))
                                        elif m.document: media.append(InputMediaDocument(m.document.file_id, caption=m.caption, caption_entities=m.caption_entities))

                                    if media:
                                        await userbot.send_media_group(target, media)

                                    processed_media_groups.add(msg.media_group_id)
                                    job["success"] += len(group_msgs)
                                except Exception as me:
                                    logger.error(f"Media group error: {me}")
                                    await userbot.copy_message(target, source, msg.id)
                                    job["success"] += 1
                        else:
                            await userbot.copy_message(target, source, msg.id)
                            job["success"] += 1

                    job["current_id"] = msg.id if msg and not msg.empty else curr_id
                    # Optimization: only update DB every 5 messages or if it's the last one
                    if job["success"] % 5 == 0 or msg.id == job["end_id"]:
                        await db.update_prof_forward_job(job_id, {
                            "success": job["success"],
                            "failed": job["failed"],
                            "skipped": job["skipped"],
                            "current_id": job["current_id"]
                        })

                curr_id += len(batch_ids)

            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
                continue # Retry batch
            except Exception as e:
                logger.error(f"Prof Forward Batch Error: {e}")
                # Fallback: process one by one if batch fails
                try:
                    msg = await userbot.get_messages(source, curr_id)
                    if not msg or msg.empty:
                        job["skipped"] += 1
                    elif not is_allowed_type(msg, filters_list):
                        job["skipped"] += 1
                    else:
                        await userbot.copy_message(target, source, curr_id)
                        job["success"] += 1
                except:
                    job["failed"] += 1

                curr_id += 1
                await db.update_prof_forward_job(job_id, {"current_id": curr_id, "success": job["success"], "failed": job["failed"], "skipped": job["skipped"]})

            # Update status message periodically (every 10 seconds)
            if time.time() - last_update > 10:
                processed = job["success"] + job["failed"] + job["skipped"]
                total = job["total"]
                percentage = (processed / total * 100) if total > 0 else 0

                elapsed = time.time() - job["start_time"]
                speed = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / speed if speed > 0 else 0

                eta_str = time.strftime("%H:%M:%S", time.gmtime(eta))

                text = (
                    f"📤 **Forwarding in Progress (Optimized)**\n\n"
                    f"Progress: `{get_progress_bar(percentage)}` `{percentage:.1f}%`\n"
                    f"✅ Completed: `{job['success']}`\n"
                    f"❌ Failed: `{job['failed']}`\n"
                    f"⏩ Skipped: `{job['skipped']}`\n"
                    f"📊 Total: `{total}`\n\n"
                    f"⚡ Speed: `{speed:.1f} msg/s`\n"
                    f"⏳ ETA: `{eta_str}`"
                )

                try:
                    await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛑 Stop", callback_data=f"prof_stop:{job_id}")]
                    ]))
                    last_update = time.time()
                except: pass

        # Final Update
        job = await db.get_prof_forward_job(job_id)
        if job and job["status"] == "running":
            await db.update_prof_forward_job(job_id, {"status": "completed"})
            await status_msg.edit_text(f"✅ **Forwarding Completed!**\n\nTotal: `{job['total']}`\nSuccess: `{job['success']}`\nFailed: `{job['failed']}`\nSkipped: `{job['skipped']}`")
        elif job and job["status"] == "stopped":
            await status_msg.edit_text(f"🛑 **Forwarding Stopped.**\n\nSuccess: `{job['success']}`")

    except Exception as e:
        logger.error(f"Worker {job_id} crashed: {e}")
    finally:
        if job_id in active_prof_tasks:
            del active_prof_tasks[job_id]

@Client.on_callback_query(filters.regex(r"^prof_stop:(.+)"))
async def prof_stop_callback(client, callback_query):
    job_id = callback_query.matches[0].group(1)
    await db.update_prof_forward_job(job_id, {"status": "stopped"})
    if job_id in active_prof_tasks:
        active_prof_tasks[job_id].cancel()
    await callback_query.answer("Stopping...")
    await callback_query.message.edit_text("🛑 Stopping job...")
