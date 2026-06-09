import asyncio
import logging
import uuid
import time
import html
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
    await db.update_user_state(user_id, "fwd_awaiting_start")
    await message.reply_text("🔗 **Forwarding Setup**\n\nPlease send the **First Message Link**.")

@Client.on_message(filters.private & (filters.text | filters.create(lambda _, __, m: m.reply_markup)) & filters.create(lambda _, __, m: not m.text or not m.text.startswith("/")), group=8)
async def handle_forward_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("fwd_awaiting_"):
        message.continue_propagation()
        return

    text = message.text.strip()

    if state == "fwd_awaiting_start":
        chat_id, first_id, _ = parse_message_link(text)
        if not chat_id:
            return await message.reply_text("❌ Invalid link. Please send a valid message link.")

        await db.update_replace_data(user_id, {"source_chat": chat_id, "start_id": first_id})
        await db.update_user_state(user_id, "fwd_awaiting_end")
        await message.reply_text("✅ Start link saved.\n\nNow send the **Last Message Link**.")

    elif state == "fwd_awaiting_end":
        data = await db.get_replace_data(user_id)
        chat_id, last_id, _ = parse_message_link(text)

        if not chat_id or chat_id != data.get("source_chat"):
             return await message.reply_text("❌ Link must be from the same channel as the start link.")

        await db.update_replace_data(user_id, {"end_id": last_id})
        await db.update_user_state(user_id, "fwd_awaiting_target")
        await message.reply_text("✅ End link saved.\n\nNow send the **Target Channel ID** or **Invite Link**.")

    elif state == "fwd_awaiting_target":
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

            try:
                for msg_id in range(job["current_id"], job["end_id"] + 1):
                    job = await db.get_forward_job(job_id)
                    if not job or job["status"] != "running":
                        break

                    try:
                        msg = await worker_client.get_messages(job["source_chat"], msg_id)
                        if not msg or msg.empty:
                            await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": msg_id + 1})
                            continue

                        # Store current message in DB so handler can access it
                        await db.forward_jobs.update_one({"job_id": job_id}, {"$set": {"active_msg_id": msg_id}})

                        # Send interaction request to user
                        has_tag = bool(msg.forward_from_chat or msg.forward_from)
                        tag_status = "Contains Forward Tag" if has_tag else "No Forward Tag"

                        buttons = [
                            [InlineKeyboardButton("🤖 Auto Mode", callback_data=f"fwd_mode:auto:{job_id}")],
                            [InlineKeyboardButton("📝 Manual Mode", callback_data=f"fwd_mode:manual:{job_id}")]
                        ]

                        await client.send_message(
                            job["user_id"],
                            f"📦 **Message {msg_id}** ({tag_status})\nChoose how to attach buttons:",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )

                        # Wait for user input (handled by callbacks)
                        # The worker will wait until the status changes or msg_id advances
                        while True:
                            check_job = await db.get_forward_job(job_id)
                            if not check_job or check_job["status"] != "running" or check_job["current_id"] > msg_id:
                                break
                            await asyncio.sleep(1)

                    except errors.FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                    except Exception as e:
                        logger.warning(f"Failed to process {msg_id}: {e}")
                        await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": msg_id + 1})

                if job["current_id"] > job["end_id"]:
                    await db.update_forward_job(job_id, {"status": "completed"})
                    await client.send_message(job["user_id"], f"🏁 **Forwarding Completed!**\n✅ Success: {job['success']}\n❌ Failed: {job['failed']}")

            finally:
                if session_string:
                    await worker_client.stop()

        except Exception as e:
            logger.error(f"Worker error on job {job_id}: {e}")
        finally:
            forward_queue.task_done()

@Client.on_callback_query(filters.regex(r"^fwd_mode:(.+):(.+)"))
async def fwd_mode_callback(client, callback_query):
    mode = callback_query.matches[0].group(1)
    job_id = callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id

    job = await db.get_forward_job(job_id)
    if not job: return

    if mode == "auto":
        config = await db.get_button_config(user_id)
        if not config or not config.get("names"):
            return await callback_query.answer("No buttons configured! Run /auto first.", show_alert=True)

        await db.update_user_state(user_id, f"fwd_collect_urls_1_{job_id}")
        await callback_query.message.edit_text(f"🔗 **Auto Mode**\nEnter URL for **{config['names'][0]}**:")

    elif mode == "manual":
        await db.update_user_state(user_id, f"fwd_manual_count_{job_id}")
        await callback_query.message.edit_text("📝 **Manual Mode**\nHow many buttons do you want to add?")

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=9)
async def handle_fwd_relay_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("fwd_"):
        message.continue_propagation()
        return

    text = message.text.strip()

    if "collect_urls" in state:
        # fwd_collect_urls_INDEX_JOBID
        parts = state.split("_")
        index = int(parts[3])
        job_id = parts[4]

        config = await db.get_button_config(user_id)
        urls = (await db.get_replace_data(user_id)).get("temp_urls", [])
        urls.append(text)
        await db.update_replace_data(user_id, {"temp_urls": urls})

        if index < config["count"]:
            await db.update_user_state(user_id, f"fwd_collect_urls_{index + 1}_{job_id}")
            await message.reply_text(f"Enter URL for **{config['names'][index]}**:")
        else:
            await db.update_user_state(user_id, None)
            await db.update_replace_data(user_id, {"temp_urls": []}) # Clear for next message
            await finish_relay_message(client, user_id, job_id, config["names"], urls)

    elif "manual_count" in state:
        job_id = state.split("_")[-1]
        if not text.isdigit(): return await message.reply_text("Enter a number.")
        count = int(text)
        await db.update_replace_data(user_id, {"temp_count": count, "temp_names": [], "temp_urls": []})
        await db.update_user_state(user_id, f"fwd_manual_name_1_{job_id}")
        await message.reply_text("Enter name for **Button 1**:")

    elif "manual_name" in state:
        parts = state.split("_")
        index = int(parts[3])
        job_id = parts[4]
        data = await db.get_replace_data(user_id)
        names = data.get("temp_names", [])
        names.append(text)
        await db.update_replace_data(user_id, {"temp_names": names})
        await db.update_user_state(user_id, f"fwd_manual_url_{index}_{job_id}")
        await message.reply_text(f"Enter URL for **{text}**:")

    elif "manual_url" in state:
        parts = state.split("_")
        index = int(parts[3])
        job_id = parts[4]
        data = await db.get_replace_data(user_id)
        urls = data.get("temp_urls", [])
        urls.append(text)
        await db.update_replace_data(user_id, {"temp_urls": urls})

        if index < data["temp_count"]:
            await db.update_user_state(user_id, f"fwd_manual_name_{index + 1}_{job_id}")
            await message.reply_text(f"Enter name for **Button {index + 1}**:")
        else:
            await db.update_user_state(user_id, f"fwd_manual_row_{job_id}")
            await message.reply_text("How many buttons per row?")

    elif "manual_row" in state:
        job_id = state.split("_")[-1]
        per_row = int(text) if text.isdigit() else 2
        data = await db.get_replace_data(user_id)
        await db.update_user_state(user_id, None)
        await finish_relay_message(client, user_id, job_id, data["temp_names"], data["temp_urls"], per_row)

async def finish_relay_message(client, user_id, job_id, names, urls, per_row=2):
    job = await db.get_forward_job(job_id)
    if not job: return

    # Get worker client
    session_string = await db.get_session(user_id)
    if session_string:
        worker = Client(f"finish_{user_id}", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=session_string, in_memory=True)
        await worker.start()
    else:
        worker = client

    try:
        msg = await worker.get_messages(job["source_chat"], job["active_msg_id"])

        buttons = []
        for i in range(0, len(names), per_row):
            row = []
            for j in range(i, min(i + per_row, len(names))):
                row.append(InlineKeyboardButton(names[j], url=urls[j]))
            buttons.append(row)

        # Copy message logic with FloodWait handling
        for attempt in range(3):
            try:
                await worker.copy_message(
                    chat_id=job["target_chat"],
                    from_chat_id=job["source_chat"],
                    message_id=job["active_msg_id"],
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                break
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                if attempt == 2: raise e
                await asyncio.sleep(1)

        await db.update_forward_job(job_id, {"success": job["success"] + 1, "current_id": job["active_msg_id"] + 1})
        await client.send_message(user_id, f"✅ Message {job['active_msg_id']} forwarded successfully!")

    except Exception as e:
        logger.error(f"Relay failed: {e}")
        await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": job["active_msg_id"] + 1})
        await client.send_message(user_id, f"❌ Failed to forward message {job['active_msg_id']}: {e}")
    finally:
        if session_string: await worker.stop()

async def init_forward_worker(client):
    active_jobs = await db.get_all_active_forward_jobs()
    for job in active_jobs:
        if job["status"] in ["running", "queued"]:
             await forward_queue.put(job["job_id"])
             logger.info(f"Resumed forward job {job['job_id']}")

    for _ in range(2): # Process 2 jobs concurrently
        asyncio.create_task(forward_worker(client))
