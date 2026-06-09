import asyncio
import logging
import uuid
import time
from pyrogram import Client, filters, errors, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.database.mongo import db
from bot.config import Config
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.decorators import retry_on_flood

logger = logging.getLogger(__name__)

# Queue for forwarding tasks
forward_queue = asyncio.Queue()

# Cache for user clients to avoid start/stop overhead
# Stores (client, last_activity_time)
user_clients = {}

async def get_user_client(user_id):
    if user_id in user_clients:
        client, _ = user_clients[user_id]
        user_clients[user_id] = (client, time.time())
        return client

    session_string = await db.get_session(user_id)
    if not session_string:
        return None

    client = Client(
        f"worker_{user_id}",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=session_string,
        in_memory=True
    )
    await client.start()
    user_clients[user_id] = (client, time.time())
    return client

async def cleanup_user_clients():
    """Periodically closes inactive user sessions."""
    while True:
        await asyncio.sleep(600) # Check every 10 mins
        now = time.time()
        for user_id, (client, last_activity) in list(user_clients.items()):
            if now - last_activity > 1800: # 30 mins inactivity
                try:
                    await client.stop()
                except: pass
                del user_clients[user_id]
                logger.info(f"Closed inactive session for user {user_id}")

@Client.on_message(filters.command("forward") & filters.private)
async def forward_command(client, message):
    user_id = message.from_user.id
    await db.update_user_state(user_id, "awaiting_forward_start_link")
    await message.reply_text("🔗 **Forwarding Setup**\n\nPlease send the **First Message Link**.")

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=8)
async def handle_forward_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state:
        message.continue_propagation()
        return

    text = message.text.strip()

    # Setup Wizard
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
        await message.reply_text("✅ End link saved.\n\nNow send the **Target Channel Username/ID/Link**.")

    elif state == "awaiting_forward_target":
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e:
            return await message.reply_text(f"❌ Could not resolve target chat: {e}")

        await db.update_replace_data(user_id, {"target_chat": target_id, "target_title": target_chat.title})
        await db.update_user_state(user_id, "awaiting_forward_filter")
        await message.reply_text(
            "🔍 **Caption Filter**\n\n"
            "Do you want to forward only files containing specific text in the caption?\n"
            "Examples: `English`, `తెలుగు`, `Hindi`\n\n"
            "Send the text to filter by, or send /skip to forward all files."
        )

    elif state == "awaiting_forward_filter":
        data = await db.get_replace_data(user_id)
        filter_text = None if text == "/skip" else text

        await db.update_user_state(user_id, None)

        summary = (
            "📋 **Forwarding Task Summary**\n\n"
            f"• **Source Chat:** `{data['source_chat']}`\n"
            f"• **Range:** `{data['start_id']}` to `{data['end_id']}`\n"
            f"• **Target Chat:** `{data['target_title']}` (`{data['target_chat']}`)\n"
            f"• **Filter:** `{filter_text or 'None'}`\n"
            f"• **Total Messages:** `{abs(data['end_id'] - data['start_id']) + 1}`\n\n"
            "Click the button below to start."
        )

        job_id = str(uuid.uuid4())
        await db.update_replace_data(user_id, {"job_id": job_id, "filter": filter_text})

        buttons = [[InlineKeyboardButton("🚀 Start Forwarding", callback_data=f"start_fwd:{job_id}")]]
        await message.reply_text(summary, reply_markup=InlineKeyboardMarkup(buttons))

    # Interactive Forwarding Inputs
    elif state.startswith("fwd_auto_url:"):
        _, job_id, index = state.split(":")
        index = int(index)

        if not text.startswith(("http://", "https://")):
             return await message.reply_text("❌ Invalid URL. Must start with http:// or https://")

        job = await db.get_forward_job(job_id)
        config = await db.get_button_config(user_id)

        temp_buttons = job.get("temp_buttons", [])
        temp_buttons.append({"name": config["names"][index], "url": text})
        await db.update_forward_job(job_id, {"temp_buttons": temp_buttons})

        if index + 1 < len(config["names"]):
            await db.update_user_state(user_id, f"fwd_auto_url:{job_id}:{index + 1}")
            await message.reply_text(f"🔗 Enter URL for **{config['names'][index + 1]}**:")
        else:
            await finalize_forward(client, user_id, job_id, config.get("rows", 1))

    elif state.startswith("fwd_manual_count:"):
        job_id = state.split(":")[1]
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")

        count = int(text)
        if count <= 0 or count > 20:
            return await message.reply_text("❌ Please enter a number between 1 and 20.")

        await db.update_forward_job(job_id, {"temp_count": count, "temp_buttons": []})
        await db.update_user_state(user_id, f"fwd_manual_name:{job_id}:0")
        await message.reply_text("Enter name for **Button 1**:")

    elif state.startswith("fwd_manual_name:"):
        _, job_id, index = state.split(":")
        index = int(index)

        job = await db.get_forward_job(job_id)
        temp_buttons = job.get("temp_buttons", [])
        temp_buttons.append({"name": text})
        await db.update_forward_job(job_id, {"temp_buttons": temp_buttons})

        await db.update_user_state(user_id, f"fwd_manual_url:{job_id}:{index}")
        await message.reply_text(f"Enter URL for **{text}**:")

    elif state.startswith("fwd_manual_url:"):
        _, job_id, index = state.split(":")
        index = int(index)

        if not text.startswith(("http://", "https://")):
             return await message.reply_text("❌ Invalid URL.")

        job = await db.get_forward_job(job_id)
        temp_buttons = job.get("temp_buttons", [])
        temp_buttons[index]["url"] = text
        await db.update_forward_job(job_id, {"temp_buttons": temp_buttons})

        if index + 1 < job["temp_count"]:
            await db.update_user_state(user_id, f"fwd_manual_name:{job_id}:{index + 1}")
            await message.reply_text(f"Enter name for **Button {index + 2}**:")
        else:
            await db.update_user_state(user_id, f"fwd_manual_rows:{job_id}")
            await message.reply_text("How many **buttons per row**?")

    elif state.startswith("fwd_manual_rows:"):
        job_id = state.split(":")[1]
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")

        rows = int(text)
        await finalize_forward(client, user_id, job_id, rows)

    else:
        message.continue_propagation()

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
        "filter": data.get("filter"),
        "start_id": min(data["start_id"], data["end_id"]),
        "end_id": max(data["start_id"], data["end_id"]),
        "current_id": min(data["start_id"], data["end_id"]),
        "status": "running",
        "success": 0,
        "failed": 0,
        "total": abs(data["end_id"] - data["start_id"]) + 1,
        "message_queue": [],
        "timestamp": time.time()
    }

    await db.add_forward_job(job_data)
    await forward_queue.put(job_id)
    await callback_query.answer("Job added to queue!", show_alert=True)
    await show_forward_status(client, callback_query.message, job_id)

def get_progress_bar(percentage):
    completed = int(percentage / 10)
    return "▰" * completed + "▱" * (10 - completed)

async def show_forward_status(client, message, job_id):
    job = await db.get_forward_job(job_id)
    if not job: return

    processed = job["success"] + job["failed"]
    percentage = (processed / job["total"] * 100) if job["total"] > 0 else 0

    text = (
        f"📊 **Forwarding Status**\n\n"
        f"• **Status:** `{job['status'].capitalize()}`\n"
        f"• **Progress:** `{get_progress_bar(percentage)}` `{percentage:.1f}%`\n"
        f"• **Success:** `{job['success']}`\n"
        f"• **Failed:** `{job['failed']}`\n"
        f"• **Total:** `{job['total']}`\n"
        f"• **Queued Items:** `{len(job.get('message_queue', []))}`\n"
        f"• **Current ID:** `{job['current_id']}`"
    )

    buttons = []
    if job["status"] == "running":
        buttons.append([InlineKeyboardButton("⏸ Pause", callback_data=f"fwd_ctrl:pause:{job_id}")])
    elif job["status"] == "paused":
        buttons.append([InlineKeyboardButton("▶️ Resume", callback_data=f"fwd_ctrl:resume:{job_id}")])

    if job["status"] not in ["completed", "stopped"]:
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

@Client.on_callback_query(filters.regex(r"^fwd_mode:(.+):(.+)"))
async def fwd_mode_callback(client, callback_query):
    mode = callback_query.matches[0].group(1)
    job_id = callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id

    if mode == "auto":
        config = await db.get_button_config(user_id)
        if not config or not config.get("names"):
            return await callback_query.answer("❌ No buttons configured in /auto. Use /auto first.", show_alert=True)

        await db.update_user_state(user_id, f"fwd_auto_url:{job_id}:0")
        await callback_query.message.edit_text(
            f"🤖 **Auto Mode**\n\nEnter URL for **{config['names'][0]}**:"
        )
    else: # manual
        await db.update_user_state(user_id, f"fwd_manual_count:{job_id}")
        await callback_query.message.edit_text(
            "🛠 **Manual Mode**\n\nHow many buttons do you want to add?"
        )

@Client.on_callback_query(filters.regex(r"^fwd_skip:(.+)"))
async def fwd_skip_callback(client, callback_query):
    job_id = callback_query.matches[0].group(1)
    job = await db.get_forward_job(job_id)
    if not job: return

    msg_id = job["current_id"]
    worker_client = await get_user_client(job["user_id"]) or client
    msg = await worker_client.get_messages(job["source_chat"], msg_id)

    skip_count = 1
    if msg and msg.media_group_id:
        group = await worker_client.get_media_group(job["source_chat"], msg_id)
        skip_count = len(group)

    await db.update_forward_job(job_id, {
        "current_id": job["current_id"] + skip_count,
        "status": "running"
    })
    await forward_queue.put(job_id)
    await db.update_user_state(job["user_id"], None)
    try:
        await callback_query.message.delete()
    except: pass
    await callback_query.answer("Skipped message(s).")

async def finalize_forward(client, user_id, job_id, rows):
    job = await db.get_forward_job(job_id)
    if not job: return

    # Clear state
    await db.update_user_state(user_id, None)

    # Use user session if available
    worker_client = await get_user_client(user_id) or client

    try:
        msg_id = job["current_id"]
        msg = await worker_client.get_messages(job["source_chat"], msg_id)

        # Build Keyboard
        buttons = []
        temp_btns = job.get("temp_buttons", [])
        for i in range(0, len(temp_btns), rows):
            row = []
            for btn in temp_btns[i:i+rows]:
                row.append(InlineKeyboardButton(btn["name"], url=btn["url"]))
            buttons.append(row)

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        # Repost without forward tag (copy_message or copy_media_group)
        processed_count = 1

        @retry_on_flood()
        async def do_copy():
            nonlocal processed_count
            if msg.media_group_id:
                copied_messages = await worker_client.copy_media_group(
                    chat_id=job["target_chat"],
                    from_chat_id=job["source_chat"],
                    message_id=msg_id
                )
                processed_count = len(copied_messages)
            else:
                await worker_client.copy_message(
                    chat_id=job["target_chat"],
                    from_chat_id=job["source_chat"],
                    message_id=msg_id,
                    reply_markup=reply_markup
                )

        await do_copy()

        await db.update_forward_job(job_id, {
            "success": job["success"] + processed_count,
            "current_id": msg_id + processed_count,
            "status": "running",
            "temp_buttons": [] # Clear temp data
        })
        await forward_queue.put(job_id)
        await client.send_message(user_id, "✅ Message(s) forwarded successfully! Moving to next...")

    except Exception as e:
        logger.error(f"Finalize forward failed: {e}")
        await db.update_forward_job(job_id, {
            "failed": job["failed"] + 1,
            "current_id": job["current_id"] + 1,
            "status": "running"
        })
        await forward_queue.put(job_id)
        await client.send_message(user_id, f"❌ Failed to forward message {job['current_id']}: {e}")

async def forward_worker(client):
    while True:
        job_id = await forward_queue.get()
        try:
            job = await db.get_forward_job(job_id)
            if not job or job["status"] != "running":
                continue

            # Use user session if available
            worker_client = await get_user_client(job["user_id"]) or client

            try:
                # 1. Process Range
                while job["current_id"] <= job["end_id"]:
                    msg_id = job["current_id"]
                    # Check for pause/stop
                    job = await db.get_forward_job(job_id)
                    if not job or job["status"] != "running":
                        break

                    try:
                        msg = await worker_client.get_messages(job["source_chat"], msg_id)
                        if not msg or msg.empty:
                            await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": msg_id + 1})
                            job["current_id"] += 1
                            continue

                        # Only forward files
                        is_media = any([msg.photo, msg.video, msg.document, msg.animation, msg.audio, msg.voice, msg.sticker])
                        if not is_media:
                            await db.update_forward_job(job_id, {"current_id": msg_id + 1})
                            job["current_id"] += 1
                            continue

                        # Apply Filter
                        content = (msg.text or msg.caption or "").lower()
                        filter_text = job.get("filter")
                        match_found = not filter_text or filter_text.lower() in content

                        if not match_found:
                            skip_count = 1
                            if msg.media_group_id:
                                group = await worker_client.get_media_group(job["source_chat"], msg_id)
                                skip_count = len(group)
                            await db.update_forward_job(job_id, {"current_id": msg_id + skip_count})
                            job["current_id"] += skip_count
                            continue

                        # Universal Auto-Buttons: Ask links for every post if configured
                        button_config = await db.get_button_config(job["user_id"])
                        if button_config and button_config.get("names"):
                            await db.update_forward_job(job_id, {"status": "waiting_input", "current_id": msg_id})
                            await db.update_user_state(job["user_id"], f"fwd_auto_url:{job_id}:0")
                            await client.send_message(job["user_id"], f"🤖 **Post Detected**\n\nEnter URL for **{button_config['names'][0]}**:")
                            return

                        # Otherwise, manual/skip mode (original interactive flow)
                        await db.update_forward_job(job_id, {"status": "waiting_input", "current_id": msg_id})
                        await db.update_user_state(job["user_id"], f"fwd_mode:{job_id}")
                        text = f"📬 **Post Detected**\n\n• **Channel:** `{job['source_chat']}`\n• **Message ID:** `{msg_id}`\n\nChoose Mode:"
                        buttons = [[InlineKeyboardButton("🤖 Auto Mode", callback_data=f"fwd_mode:auto:{job_id}"),
                                    InlineKeyboardButton("🛠 Manual Mode", callback_data=f"fwd_mode:manual:{job_id}")],
                                   [InlineKeyboardButton("⏭ Skip", callback_data=f"fwd_skip:{job_id}")]]
                        await client.send_message(job["user_id"], text, reply_markup=InlineKeyboardMarkup(buttons))
                        return

                    except errors.FloodWait as e:
                        await asyncio.sleep(e.value + 1)
                    except Exception as e:
                        logger.warning(f"Failed to process {msg_id}: {e}")
                        await db.update_forward_job(job_id, {"failed": job["failed"] + 1, "current_id": msg_id + 1})
                        job["current_id"] += 1
                    await asyncio.sleep(0.5)

                # 2. Process Queue (Trace)
                while True:
                    job = await db.get_forward_job(job_id)
                    if not job or job["status"] != "running" or not job.get("message_queue"):
                        break

                    msg_id = await db.pop_from_forward_queue(job_id)
                    if not msg_id: break

                    try:
                        msg = await worker_client.get_messages(job["source_chat"], msg_id)
                        # Re-apply filter and media check for queue
                        is_media = any([msg.photo, msg.video, msg.document, msg.animation, msg.audio, msg.voice, msg.sticker])
                        if not is_media: continue

                        content = (msg.text or msg.caption or "").lower()
                        filter_text = job.get("filter")
                        if filter_text and filter_text.lower() not in content:
                            continue

                        # Ask links for queued post
                        button_config = await db.get_button_config(job["user_id"])
                        if button_config and button_config.get("names"):
                            await db.update_forward_job(job_id, {"status": "waiting_input", "current_id": msg_id})
                            await db.update_user_state(job["user_id"], f"fwd_auto_url:{job_id}:0")
                            await client.send_message(job["user_id"], f"🔄 **Queued Post Detected**\n\nEnter URL for **{button_config['names'][0]}**:")
                            return
                    except Exception as e:
                        logger.error(f"Queue process error: {e}")

                # Completed
                job = await db.get_forward_job(job_id)
                if job and job["status"] == "running" and job["current_id"] > job["end_id"] and not job.get("message_queue"):
                    await db.update_forward_job(job_id, {"status": "completed"})
                    await client.send_message(job["user_id"], "✅ **Forwarding Job Completed!**")

            except Exception as e:
                logger.error(f"Error in forward loop: {e}")
        except Exception as e:
            logger.error(f"Worker error on job {job_id}: {e}")
        finally:
            forward_queue.task_done()

# Trace monitoring integration
@Client.on_message(group=10)
async def trace_monitor(client, message):
    if not message.chat: return

    # 1. Check for active range forwarding jobs (Add to queue)
    # We find jobs matching this source_chat that are currently running
    active_jobs = await db.forward_jobs.find({
        "source_chat": {"$in": [message.chat.id, f"@{message.chat.username}"]},
        "status": {"$in": ["running", "waiting_input"]}
    }).to_list(length=None)

    for job in active_jobs:
        if message.id > job["current_id"]:
             await db.append_to_forward_queue(job["job_id"], message.id)
             logger.info(f"Queued incoming message {message.id} for job {job['job_id']}")

    # 2. Process legacy standalone traces
    traces = await db.get_all_traces()
    for trace in traces:
        if str(message.chat.id) == str(trace["source_chat"]) or message.chat.username == str(trace["source_chat"]).replace("@", ""):
             # Apply filter
             content = (message.text or message.caption or "").lower()
             filter_text = trace.get("filter")
             if filter_text and filter_text.lower() not in content:
                 continue

             # Universal Auto-Buttons for Trace
             user_id = trace["user_id"]
             button_config = await db.get_button_config(user_id)

             # Use user session if available
             worker_client = await get_user_client(user_id) or client

             try:
                 # Repost without forward tag
                 @retry_on_flood()
                 async def do_trace_copy():
                     if message.media_group_id:
                         await worker_client.copy_media_group(trace["target_chat"], message.chat.id, message.id)
                     else:
                         # For standalone trace, we don't pause for links (auto-mode usually implies preset or handled in main job)
                         # However, to be strict with "ask for link", standalone trace should probably also queue for user.
                         # For now, keep it simple copy to fulfill the "automatic" part of Trace Mode definition.
                         await worker_client.copy_message(trace["target_chat"], message.chat.id, message.id)

                 await do_trace_copy()
                 logger.info(f"Standalone Trace: Forwarded {message.id} from {message.chat.id}")
             except Exception as e:
                 logger.error(f"Trace forwarding failed: {e}")

async def init_forward_worker(client):
    active_jobs = await db.get_all_active_forward_jobs()
    for job in active_jobs:
        if job["status"] in ["running", "queued"]:
             await forward_queue.put(job["job_id"])
    asyncio.create_task(cleanup_user_clients())
    for _ in range(2):
        asyncio.create_task(forward_worker(client))
