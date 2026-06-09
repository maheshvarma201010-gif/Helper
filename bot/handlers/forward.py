import asyncio
import logging
import uuid
import time
from pyrogram import Client, filters, errors, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.database.mongo import db
from bot.config import Config
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.replacer import render_message_to_html

logger = logging.getLogger(__name__)

# Queue for forwarding tasks
forward_queue = asyncio.Queue()

@Client.on_message(filters.command("forward") & filters.private)
async def forward_command(client, message):
    user_id = message.from_user.id
    await db.update_user_state(user_id, "awaiting_forward_start_link")
    await message.reply_text("🔗 **Forwarding Setup**\n\nPlease send the **First Message Link**.")

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=8)
async def handle_forward_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("awaiting_forward_"):
        message.continue_propagation()
        return

    text = message.text.strip()

    if state == "awaiting_forward_start_link":
        chat_id, first_id, _ = parse_message_link(text)
        if not chat_id:
            return await message.reply_text("❌ Invalid link. Please send a valid message link.")

        await db.update_replace_data(user_id, {"source_chat": chat_id, "start_id": first_id})
        await db.update_user_state(user_id, "awaiting_forward_end_link")
        await message.reply_text("✅ Start link saved.\n\nNow send the **Last Message Link**.")

    elif state == "awaiting_forward_end_link":
        data = await db.get_replace_data(user_id)
        chat_id, last_id, _ = parse_message_link(text)

        if not chat_id or chat_id != data.get("source_chat"):
             return await message.reply_text("❌ Link must be from the same channel as the start link.")

        await db.update_replace_data(user_id, {"end_id": last_id})
        await db.update_user_state(user_id, "awaiting_forward_target")
        await message.reply_text("✅ End link saved.\n\nNow send the **Target Channel ID** or **Invite Link**.")

    elif state == "awaiting_forward_target":
        data = await db.get_replace_data(user_id)
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e:
            return await message.reply_text(f"❌ Could not resolve target chat: {e}")

        await db.update_user_state(user_id, None)

        summary = (
            "📋 **Forwarding Task Summary**\n\n"
            f"• **Source Chat:** `{data['source_chat']}`\n"
            f"• **Range:** `{data['start_id']}` to `{data['end_id']}`\n"
            f"• **Target Chat:** `{target_chat.title}` (`{target_id}`)\n"
            f"• **Total Messages:** `{abs(data['end_id'] - data['start_id']) + 1}`\n\n"
            "Click the button below to start."
        )

        job_id = str(uuid.uuid4())
        await db.update_replace_data(user_id, {"job_id": job_id, "target_chat": target_id})

        buttons = [[InlineKeyboardButton("🚀 Start Forwarding", callback_data=f"start_fwd:{job_id}")]]
        await message.reply_text(summary, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^start_fwd:(.+)"))
async def start_fwd_callback(client, callback_query):
    job_id = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id

    data = await db.get_replace_data(user_id)
    if not data or data.get("job_id") != job_id:
        return await callback_query.answer("Session expired. Setup again.", show_alert=True)

    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "source_chat": data["source_chat"],
        "target_chat": data["target_chat"],
        "start_id": min(data["start_id"], data["end_id"]),
        "end_id": max(data["start_id"], data["end_id"]),
        "current_id": min(data["start_id"], data["end_id"]),
        "status": "queued",
        "success": 0,
        "failed": 0,
        "total": abs(data["end_id"] - data["start_id"]) + 1,
        "timestamp": time.time()
    }

    await db.add_forward_job(job_data)
    await forward_queue.put(job_id)
    await callback_query.answer("Job added to queue!", show_alert=True)
    await show_forward_status(client, callback_query.message, job_id)

async def show_forward_status(client, message, job_id):
    job = await db.get_forward_job(job_id)
    if not job: return

    progress = (job["success"] + job["failed"]) / job["total"] * 100
    text = (
        f"📊 **Forwarding Status**\n\n"
        f"• **Status:** `{job['status'].capitalize()}`\n"
        f"• **Progress:** `{progress:.1f}%`\n"
        f"• **Success:** `{job['success']}`\n"
        f"• **Failed:** `{job['failed']}`\n"
        f"• **Total:** `{job['total']}`\n"
        f"• **Current ID:** `{job['current_id']}`"
    )

    buttons = []
    if job["status"] == "running":
        buttons.append([InlineKeyboardButton("⏸ Pause", callback_data=f"fwd_ctrl:pause:{job_id}")])
    elif job["status"] == "paused":
        buttons.append([InlineKeyboardButton("▶️ Resume", callback_data=f"fwd_ctrl:resume:{job_id}")])

    if job["status"] != "completed" and job["status"] != "stopped":
        buttons.append([InlineKeyboardButton("🛑 Stop", callback_data=f"fwd_ctrl:stop:{job_id}")])

    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
    except: pass

@Client.on_callback_query(filters.regex(r"^fwd_ctrl:(.+):(.+)"))
async def fwd_ctrl_callback(client, callback_query):
    action = callback_query.matches[0].group(1)
    job_id = callback_query.matches[0].group(2)

    if action == "stop":
        await db.update_forward_job(job_id, {"status": "stopped"})
        await callback_query.answer("Stopped.")
    elif action == "pause":
        await db.update_forward_job(job_id, {"status": "paused"})
        await callback_query.answer("Paused.")
    elif action == "resume":
        await db.update_forward_job(job_id, {"status": "running"})
        await forward_queue.put(job_id)
        await callback_query.answer("Resuming...")

    await show_forward_status(client, callback_query.message, job_id)

async def forward_worker(client):
    while True:
        job_id = await forward_queue.get()
        try:
            job = await db.get_forward_job(job_id)
            if not job or job["status"] in ["completed", "stopped"]:
                continue

            await db.update_forward_job(job_id, {"status": "running"})

            # Use user session if available
            session_string = await db.get_session(job["user_id"])
            if session_string:
                worker_client = Client(
                    f"worker_{job['user_id']}",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await worker_client.start()
            else:
                worker_client = client

            button_config = await db.get_button_config(job["user_id"])

            try:
                for msg_id in range(job["current_id"], job["end_id"] + 1):
                    # Check for pause/stop
                    job = await db.get_forward_job(job_id)
                    if not job or job["status"] != "running":
                        break

                    try:
                        msg = await worker_client.get_messages(job["source_chat"], msg_id)
                        if not msg or msg.empty:
                            await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": msg_id + 1})
                            continue

                        # Handle auto-buttons
                        reply_markup = None
                        if button_config and button_config.get("tag"):
                            content = msg.text or msg.caption or ""
                            if button_config["tag"].lower() in content.lower():
                                buttons = []
                                for name, url in zip(button_config["names"], button_config["urls"]):
                                    buttons.append([InlineKeyboardButton(name, url=url)])
                                reply_markup = InlineKeyboardMarkup(buttons)

                        # Copy message
                        await worker_client.copy_message(
                            chat_id=job["target_chat"],
                            from_chat_id=job["source_chat"],
                            message_id=msg_id,
                            reply_markup=reply_markup or msg.reply_markup
                        )

                        await db.update_forward_job(job_id, {"success": job["success"] + 1, "current_id": msg_id + 1})

                    except errors.FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                        # Retry once
                        await worker_client.copy_message(job["target_chat"], job["source_chat"], msg_id, reply_markup=reply_markup or msg.reply_markup)
                        await db.update_forward_job(job_id, {"success": job["success"] + 1, "current_id": msg_id + 1})
                    except Exception as e:
                        logger.warning(f"Failed to forward {msg_id}: {e}")
                        await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": msg_id + 1})

                    await asyncio.sleep(0.5) # Speed control

                if job["current_id"] > job["end_id"]:
                    await db.update_forward_job(job_id, {"status": "completed"})

            finally:
                if session_string:
                    await worker_client.stop()

        except Exception as e:
            logger.error(f"Worker error on job {job_id}: {e}")
        finally:
            forward_queue.task_done()

async def init_forward_worker(client):
    active_jobs = await db.get_all_active_forward_jobs()
    for job in active_jobs:
        if job["status"] in ["running", "queued"]:
             await forward_queue.put(job["job_id"])
             logger.info(f"Resumed forward job {job['job_id']}")

    for _ in range(2): # Process 2 jobs concurrently
        asyncio.create_task(forward_worker(client))
