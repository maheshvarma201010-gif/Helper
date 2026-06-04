import asyncio
import os
import time
import logging
import uuid
from pyrogram import Client, filters, enums, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.watermark import apply_watermark
from bot.utils.replacer import render_message_to_html

logger = logging.getLogger(__name__)

# Global task queue to handle concurrency
tedit_queue = asyncio.Queue()

@Client.on_message(filters.command("tedit_status") & filters.private)
async def tedit_status_command(client, message):
    user_id = message.from_user.id
    job = await db.get_active_tedit_job(user_id)

    if not job:
        return await message.reply_text("No active TEdit jobs found.")

    text = (
        f"📊 **TEdit Job Status**\n\n"
        f"• **Job ID:** `{job['job_id']}`\n"
        f"• **Status:** `{job['status'].capitalize()}`\n"
        f"• **Type:** `{job['type']}`\n"
        f"• **Processed:** `{job.get('total_processed', 0)}` messages\n"
        f"• **Errors:** `{job.get('total_errors', 0)}`"
    )

    if job['type'] == 'range':
        progress = ((job['current_id'] - job['start_id'] + 1) / (job['end_id'] - job['start_id'] + 1)) * 100
        text += f"\n• **Progress:** `{progress:.1f}%` ({job['current_id']}/{job['end_id']})"

    buttons = []
    if job['status'] == 'running':
        buttons.append([InlineKeyboardButton("⏸ Pause", callback_data=f"tedit_job:pause:{job['job_id']}")])
    elif job['status'] == 'paused':
        buttons.append([InlineKeyboardButton("▶️ Resume", callback_data=f"tedit_job:resume:{job['job_id']}")])

    if job['status'] in ['running', 'paused', 'queued']:
        buttons.append([InlineKeyboardButton("🛑 Stop", callback_data=f"tedit_job:stop:{job['job_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

@Client.on_message(filters.command(["tedit_stop", "tedit_pause", "tedit_resume"]) & filters.private)
async def tedit_control_commands(client, message):
    user_id = message.from_user.id
    cmd = message.command[0].replace("tedit_", "")
    job = await db.get_active_tedit_job(user_id)

    if not job:
        return await message.reply_text("No active TEdit jobs found.")

    if cmd == "stop":
        await db.update_tedit_job(job['job_id'], {"status": "cancelled"})
        await message.reply_text("✅ Job stopped.")
    elif cmd == "pause":
        await db.update_tedit_job(job['job_id'], {"status": "paused"})
        await message.reply_text("✅ Job paused.")
    elif cmd == "resume":
        await db.update_tedit_job(job['job_id'], {"status": "running"})
        # We don't need to re-add to queue if it was already in queue or paused
        # but the worker checks status continuously.
        await message.reply_text("✅ Job resumed.")

@Client.on_callback_query(filters.regex(r"^tedit_job:(.+):(.+)"))
async def handle_job_callbacks(client, callback_query):
    action = callback_query.matches[0].group(1)
    job_id = callback_query.matches[0].group(2)

    if action == "stop":
        await db.update_tedit_job(job_id, {"status": "cancelled"})
        await callback_query.answer("Job stopped.")
    elif action == "pause":
        await db.update_tedit_job(job_id, {"status": "paused"})
        await callback_query.answer("Job paused.")
    elif action == "resume":
        await db.update_tedit_job(job_id, {"status": "running"})
        await callback_query.answer("Job resumed.")

    # Refresh status message
    await tedit_status_command(client, callback_query.message)

@Client.on_message(filters.command("tedit") & filters.private)
async def tedit_range_command(client, message):
    if len(message.command) < 2:
        return # Handled by tedit_setup.py

    user_id = message.from_user.id
    settings = await db.get_tedit_settings(user_id)
    if not settings:
        return await message.reply_text("Please setup your watermark first using /tedit")

    args = message.command[1:]

    # Check if it's a channel ID for monitoring
    if len(args) == 1 and (args[0].startswith("-100") or args[0].isdigit()):
        try:
            chat_id = int(args[0])
            chat = await resolve_chat(client, chat_id)

            # Check permissions
            member = await chat.get_member(client.me.id)
            if not member.privileges or not member.privileges.can_edit_messages:
                return await message.reply_text("❌ I need 'Edit Messages' permission in that channel.")

            # Toggle monitoring
            current = await db.get_user_monitoring(user_id)
            is_monitored = any(m["channel_id"] == chat.id for m in current)

            await db.set_tedit_monitoring(user_id, chat.id, not is_monitored)
            status_text = "Enabled" if not is_monitored else "Disabled"
            return await message.reply_text(f"✅ Monitoring {status_text} for `{chat.title}` ({chat.id})")
        except Exception as e:
            return await message.reply_text(f"❌ Error: {e}")

    # Message Range Mode
    if len(args) >= 2:
        start_link = args[0]
        end_link = args[1]

        chat_id, start_id, _ = parse_message_link(start_link)
        chat_id_end, end_id, _ = parse_message_link(end_link)

        if not chat_id or not chat_id_end or chat_id != chat_id_end:
            return await message.reply_text("❌ Invalid links or different channels.")

        try:
            chat = await resolve_chat(client, chat_id)
            # Check permissions
            member = await chat.get_member(client.me.id)
            if not member.privileges or not member.privileges.can_edit_messages:
                return await message.reply_text("❌ I need 'Edit Messages' permission in that channel.")
        except Exception as e:
            return await message.reply_text(f"❌ Error resolving chat: {e}")

        job_id = str(uuid.uuid4())
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "chat_id": chat.id,
            "start_id": min(start_id, end_id),
            "end_id": max(start_id, end_id),
            "current_id": min(start_id, end_id),
            "status": "queued",
            "type": "range",
            "total_processed": 0,
            "total_errors": 0,
            "timestamp": time.time()
        }
        await db.add_tedit_job(job_data)
        await tedit_queue.put(job_id)
        await message.reply_text(f"✅ TEdit Job Queued! (ID: `{job_id}`)\nUse /tedit_status to track progress.")

@Client.on_message(filters.channel)
async def tedit_monitor_handler(client, message):
    chat_id = message.chat.id
    monitors = await db.get_tedit_monitoring(chat_id)

    if not monitors:
        return

    # We process for each user who monitors this channel
    for monitor in monitors:
        user_id = monitor["user_id"]
        settings = await db.get_tedit_settings(user_id)
        if not settings: continue

        # Add to queue as a high-priority "single" task
        job_id = str(uuid.uuid4())
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message.id,
            "status": "queued",
            "type": "monitor",
            "timestamp": time.time()
        }
        await db.add_tedit_job(job_data)
        await tedit_queue.put(job_id)

async def tedit_worker(client):
    while True:
        job_id = await tedit_queue.get()
        try:
            job = await db.get_tedit_job(job_id)
            if not job or job["status"] == "cancelled":
                continue

            await db.update_tedit_job(job_id, {"status": "running"})

            if job["type"] == "range":
                await process_range_job(client, job)
            else:
                await process_single_job(client, job)

        except Exception as e:
            logger.error(f"Worker error on job {job_id}: {e}")
        finally:
            tedit_queue.task_done()

async def process_range_job(client, job):
    job_id = job["job_id"]
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    start_id = job["current_id"]
    end_id = job["end_id"]

    settings = await db.get_tedit_settings(user_id)
    media_path = None
    if settings.get("type") in ["logo", "sticker"]:
        media_file_id = settings.get("media_file_id")
        if media_file_id:
            media_path = await client.download_media(media_file_id)

    try:
        for msg_id in range(start_id, end_id + 1):
            # Check if job is still active
            job = await db.get_tedit_job(job_id)
            if not job or job["status"] != "running":
                break

            try:
                msg = await client.get_messages(chat_id, msg_id)
                if not msg or msg.empty: continue

                if await process_message_watermark(client, msg, settings, media_path):
                    await db.update_tedit_job(job_id, {
                        "current_id": msg_id,
                        "total_processed": job["total_processed"] + 1
                    })

                await asyncio.sleep(0.5) # Flood protection
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logger.warning(f"Error processing {msg_id}: {e}")
                await db.update_tedit_job(job_id, {"total_errors": job.get("total_errors", 0) + 1})

        await db.update_tedit_job(job_id, {"status": "completed"})
    finally:
        if media_path and os.path.exists(media_path): os.remove(media_path)

async def process_single_job(client, job):
    job_id = job["job_id"]
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    msg_id = job["message_id"]

    settings = await db.get_tedit_settings(user_id)
    media_path = None
    if settings.get("type") in ["logo", "sticker"]:
        media_file_id = settings.get("media_file_id")
        if media_file_id:
            media_path = await client.download_media(media_file_id)

    try:
        msg = await client.get_messages(chat_id, msg_id)
        if msg and not msg.empty:
            await process_message_watermark(client, msg, settings, media_path)
        await db.update_tedit_job(job_id, {"status": "completed"})
    finally:
        if media_path and os.path.exists(media_path): os.remove(media_path)

async def process_message_watermark(client, msg, settings, watermark_media_path):
    """
    Core logic to process a single message's media and update/replace it.
    """
    if not msg:
        return False

    # Handle FloodWait globally at worker level, but also here for safety
    # and handle expired file references
    photo = msg.photo
    if not photo and msg.document and msg.document.mime_type.startswith("image/"):
        photo = msg.document

    if not photo:
        return False

    try:
        # Download
        try:
            path = await client.download_media(msg)
        except errors.FileReferenceExpired:
            logger.info(f"File reference expired for {msg.id}, refreshing...")
            msg = await client.get_messages(msg.chat.id, msg.id)
            path = await client.download_media(msg)
        if not path: return False

        # Apply watermark
        processed_bytes = apply_watermark(path, settings, watermark_media_path)
        os.remove(path)

        if not processed_bytes: return False

        # Determine if we can edit
        # Note: Bot API allows editing media only in certain conditions,
        # but Pyrogram edit_message_media usually works for channels if bot is admin.

        # Preserve metadata
        caption = render_message_to_html(msg.caption, msg.caption_entities) if msg.caption else None
        reply_markup = msg.reply_markup

        from pyrogram.types import InputMediaPhoto

        # Save processed to a temp file for upload
        temp_out = f"processed_{msg.id}_{uuid.uuid4().hex[:8]}.jpg"
        with open(temp_out, "wb") as f:
            f.write(processed_bytes.getvalue())

        try:
            await client.edit_message_media(
                chat_id=msg.chat.id,
                message_id=msg.id,
                media=InputMediaPhoto(temp_out, caption=caption, parse_mode=enums.ParseMode.HTML),
                reply_markup=reply_markup
            )
        except (errors.MessageIdInvalid, errors.MessageNotModified, errors.ChatAdminRequired, Exception) as e:
            logger.info(f"Could not edit message {msg.id}, attempting re-upload: {e}")

            # Re-upload logic
            try:
                await client.send_photo(
                    chat_id=msg.chat.id,
                    photo=temp_out,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=reply_markup
                )
                # Optionally delete old message if possible
                try:
                    await client.delete_messages(msg.chat.id, msg.id)
                except: pass
            except Exception as re_e:
                logger.error(f"Failed to re-upload {msg.id}: {re_e}")
                if os.path.exists(temp_out): os.remove(temp_out)
                return False

        if os.path.exists(temp_out): os.remove(temp_out)
        return True
    except Exception as e:
        logger.error(f"Error in process_message_watermark: {e}")
        return False

# Initialize worker and resume pending jobs
async def init_worker(client, concurrency=3):
    logger.info(f"Initializing TEdit worker (concurrency={concurrency}) and resuming pending jobs...")
    active_jobs = await db.get_all_active_tedit_jobs()
    for job in active_jobs:
        if job["status"] in ["running", "queued"]:
            await tedit_queue.put(job["job_id"])
            logger.info(f"Resumed job {job['job_id']}")

    for _ in range(concurrency):
        asyncio.create_task(tedit_worker(client))
