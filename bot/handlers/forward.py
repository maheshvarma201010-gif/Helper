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
        await asyncio.sleep(600)
        now = time.time()
        for user_id, (client, last_activity) in list(user_clients.items()):
            if now - last_activity > 1800:
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
            return await message.reply_text("❌ Invalid link.")

        await db.update_replace_data(user_id, {"source_chat": chat_id, "start_id": first_id})
        await db.update_user_state(user_id, "awaiting_forward_end_link")
        await message.reply_text("✅ Start link saved.\n\nNow send the **Last Message Link**.")

    elif state == "awaiting_forward_end_link":
        data = await db.get_replace_data(user_id)
        chat_id, last_id, _ = parse_message_link(text)
        if not chat_id or chat_id != data.get("source_chat"):
             return await message.reply_text("❌ Link must be from the same channel.")

        await db.update_replace_data(user_id, {"end_id": last_id})
        await db.update_user_state(user_id, "awaiting_forward_target")
        await message.reply_text("✅ End link saved.\n\nNow send the **Target Channel Username/ID/Link**.")

    elif state == "awaiting_forward_target":
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e:
            return await message.reply_text(f"❌ Could not resolve target: {e}")

        await db.update_replace_data(user_id, {"target_chat": target_id, "target_title": target_chat.title})
        await db.update_user_state(user_id, "awaiting_forward_filter")
        await message.reply_text("🔍 **Caption Filter**\n\nDo you want to forward only files containing specific text? (English, తెలుగు, etc.)\n\nSend text to filter or /skip.")

    elif state == "awaiting_forward_filter":
        data = await db.get_replace_data(user_id)
        filter_text = None if text == "/skip" else text

        await db.update_replace_data(user_id, {"filter": filter_text})
        await db.update_user_state(user_id, "awaiting_forward_trace")

        buttons = [[InlineKeyboardButton("🔍 Trace", callback_data="fwd_setup_mode:trace"),
                    InlineKeyboardButton("🏁 Finish", callback_data="fwd_setup_mode:finish")]]
        await message.reply_text("⚙️ **Select Completion Mode:**\n\nShould I monitor and forward new messages (Trace) or stop after the range (Finish)?", reply_markup=InlineKeyboardMarkup(buttons))

    elif state == "awaiting_forward_trace":
        # Handle manual text input if user doesn't use buttons
        await message.reply_text("Please use the buttons above to select Trace or Finish.")

    # DM Interactive Flow
    elif state.startswith("dm_auto_url:"):
        _, msg_id, index = state.split(":")
        index = int(index)
        if not text.startswith("http"):
             return await message.reply_text("❌ Invalid URL.")

        config = await db.get_button_config(user_id)
        await db.users.update_one({"user_id": user_id}, {"$push": {"temp_dm_links": {"name": config["names"][index], "url": text}}})

        if index + 1 < len(config["names"]):
            await db.update_user_state(user_id, f"dm_auto_url:{msg_id}:{index + 1}")
            await message.reply_text(f"🔗 Enter URL for **{config['names'][index + 1]}**:")
        else:
            await db.update_user_state(user_id, f"dm_target_chat:{msg_id}")
            await message.reply_text("✅ All links saved.\n\nNow send the **Target Channel ID/Username**:")

    elif state.startswith("dm_target_chat:"):
        msg_id = int(state.split(":")[1])
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e:
            return await message.reply_text(f"❌ Error: {e}")

        user_data = await db.get_user(user_id)
        temp_links = user_data.get("temp_dm_links", [])

        buttons = []
        rows = (await db.get_button_config(user_id)).get("rows", 1)
        for i in range(0, len(temp_links), rows):
            row = []
            for btn in temp_links[i:i+rows]:
                row.append(InlineKeyboardButton(btn["name"], url=btn["url"]))
            buttons.append(row)

        worker_client = await get_user_client(user_id) or client
        try:
            await worker_client.copy_message(target_id, user_id, msg_id, reply_markup=InlineKeyboardMarkup(buttons))
            await message.reply_text("✅ Successfully forwarded to channel!")
        except Exception as e:
            await message.reply_text(f"❌ Forward failed: {e}")

        await db.update_user_state(user_id, None)
        await db.users.update_one({"user_id": user_id}, {"$unset": {"temp_dm_links": ""}})

    elif state.startswith("dm_manual_"):
        # Placeholder for manual mode if needed, focusing on auto as primary
        pass

    else:
        message.continue_propagation()

@Client.on_callback_query(filters.regex(r"^fwd_setup_mode:(.+)"))
async def fwd_setup_mode_callback(client, callback_query):
    mode = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    data = await db.get_replace_data(user_id)

    await db.update_user_state(user_id, None)

    job_id = str(uuid.uuid4())
    await db.update_replace_data(user_id, {"job_id": job_id, "mode": mode})

    summary = (
        f"📋 **Forwarding Task Summary**\n\n• **Source:** `{data['source_chat']}`\n• **Target:** `{data['target_title']}`\n"
        f"• **Range:** `{data['start_id']}`-`{data['end_id']}`\n• **Filter:** `{data.get('filter') or 'None'}`\n• **Mode:** `{mode.capitalize()}`"
    )
    buttons = [[InlineKeyboardButton("🚀 Start Forwarding", callback_data=f"start_fwd:{job_id}")]]
    await callback_query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_message(filters.private & (filters.photo | filters.video | filters.document | filters.animation | filters.audio | filters.voice | filters.sticker), group=9)
async def handle_dm_media(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)
    if state: return

    buttons = [[InlineKeyboardButton("🤖 Auto Mode", callback_data=f"dm_mode:auto:{message.id}"),
                InlineKeyboardButton("🛠 Manual Mode", callback_data=f"dm_mode:manual:{message.id}")]]
    await message.reply_text("📬 **Post Detected in DM**\n\nChoose Mode for forwarding:", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^dm_mode:(.+):(.+)"))
async def dm_mode_callback(client, callback_query):
    mode, msg_id = callback_query.matches[0].group(1), callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id

    if mode == "auto":
        config = await db.get_button_config(user_id)
        if not config or not config.get("names"):
            return await callback_query.answer("❌ No buttons configured. Use /auto first.", show_alert=True)

        await db.users.update_one({"user_id": user_id}, {"$set": {"temp_dm_links": []}})
        await db.update_user_state(user_id, f"dm_auto_url:{msg_id}:0")
        await callback_query.message.edit_text(f"🤖 **Auto Mode**\n\nEnter URL for **{config['names'][0]}**:")
    else:
        await callback_query.answer("Manual mode not yet implemented for DM. Use Auto Mode.", show_alert=True)

@Client.on_callback_query(filters.regex(r"^start_fwd:(.+)"))
async def start_fwd_callback(client, callback_query):
    job_id = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    data = await db.get_replace_data(user_id)

    job_data = {
        "job_id": job_id, "user_id": user_id, "source_chat": data["source_chat"],
        "target_chat": data["target_chat"], "filter": data.get("filter"),
        "start_id": min(data["start_id"], data["end_id"]), "end_id": max(data["start_id"], data["end_id"]),
        "current_id": min(data["start_id"], data["end_id"]), "status": "running",
        "success": 0, "failed": 0, "total": abs(data["end_id"] - data["start_id"]) + 1,
        "mode": data.get("mode", "finish"), "message_queue": [], "timestamp": time.time()
    }
    await db.add_forward_job(job_data)
    await forward_queue.put(job_id)
    await callback_query.answer("Job started!")
    await show_forward_status(client, callback_query.message, job_id)

def get_progress_bar(percentage):
    completed = int(percentage / 10)
    return "▰" * completed + "▱" * (10 - completed)

async def show_forward_status(client, message, job_id):
    job = await db.get_forward_job(job_id)
    if not job: return
    processed = job["success"] + job["failed"]
    percentage = (processed / job["total"] * 100) if job["total"] > 0 else 0
    text = (f"📊 **Forwarding Status**\n\n• **Status:** `{job['status'].capitalize()}`\n"
            f"• **Progress:** `{get_progress_bar(percentage)}` `{percentage:.1f}%`\n"
            f"• **Success:** `{job['success']}`\n• **Failed:** `{job['failed']}`\n"
            f"• **Total:** `{job['total']}`\n• **Queue:** `{len(job.get('message_queue', []))}`")

    buttons = [[InlineKeyboardButton("🛑 Stop", callback_data=f"fwd_ctrl:stop:{job_id}")]]
    try: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except: pass

@Client.on_callback_query(filters.regex(r"^fwd_ctrl:(.+):(.+)"))
async def fwd_ctrl_callback(client, callback_query):
    action, job_id = callback_query.matches[0].group(1), callback_query.matches[0].group(2)
    if action == "stop":
        await db.update_forward_job(job_id, {"status": "stopped"})
        await callback_query.answer("Stopped.")
    await show_forward_status(client, callback_query.message, job_id)

async def forward_worker(client):
    while True:
        job_id = await forward_queue.get()
        try:
            job = await db.get_forward_job(job_id)
            if not job or job["status"] != "running": continue
            worker_client = await get_user_client(job["user_id"]) or client

            async def process_msg(msg_id):
                try:
                    msg = await worker_client.get_messages(job["source_chat"], msg_id)
                    if not msg or msg.empty: return False, 1
                    is_media = any([msg.photo, msg.video, msg.document, msg.animation, msg.audio, msg.voice, msg.sticker])
                    if not is_media: return False, 1
                    content = (msg.text or msg.caption or "").lower()
                    if job.get("filter") and job["filter"].lower() not in content:
                        count = len(await worker_client.get_media_group(job["source_chat"], msg_id)) if msg.media_group_id else 1
                        return False, count
                    if msg.media_group_id:
                        copied = await worker_client.copy_media_group(job["target_chat"], job["source_chat"], msg_id)
                        return True, len(copied)
                    else:
                        await worker_client.copy_message(job["target_chat"], job["source_chat"], msg_id)
                        return True, 1
                except Exception as e:
                    logger.error(f"Worker process error: {e}")
                    return False, 1

            # 1. Range
            while job["current_id"] <= job["end_id"]:
                job = await db.get_forward_job(job_id)
                if not job or job["status"] != "running": break
                success, count = await process_msg(job["current_id"])
                if success: await db.update_forward_job(job_id, {"success": job["success"] + count, "current_id": job["current_id"] + count})
                else: await db.update_forward_job(job_id, {"failed": job["failed"] + count, "current_id": job["current_id"] + count})
                await asyncio.sleep(1)

            # 2. Queue (Trace)
            while True:
                job = await db.get_forward_job(job_id)
                if not job or job["status"] != "running": break
                msg_id = await db.pop_from_forward_queue(job_id)
                if not msg_id:
                    if job.get("mode") == "trace":
                         await asyncio.sleep(5)
                         continue
                    else: break

                success, count = await process_msg(msg_id)
                if success: await db.update_forward_job(job_id, {"success": job["success"] + count})
                else: await db.update_forward_job(job_id, {"failed": job["failed"] + count})

            await db.update_forward_job(job_id, {"status": "completed"})
            await client.send_message(job["user_id"], "✅ Forwarding Job Completed!")

        except Exception as e: logger.error(f"Worker error: {e}")
        finally: forward_queue.task_done()

@Client.on_message(group=10)
async def trace_monitor(client, message):
    if not message.chat: return
    active_jobs = await db.forward_jobs.find({
        "source_chat": {"$in": [message.chat.id, f"@{message.chat.username}"]},
        "status": {"$in": ["running", "waiting_input"]}
    }).to_list(length=None)
    for job in active_jobs:
        if message.id > job["current_id"]:
             await db.append_to_forward_queue(job["job_id"], message.id)

async def init_forward_worker(client):
    active_jobs = await db.get_all_active_forward_jobs()
    for job in active_jobs:
        if job["status"] in ["running", "queued"]: await forward_queue.put(job["job_id"])
    asyncio.create_task(cleanup_user_clients())
    for _ in range(2): asyncio.create_task(forward_worker(client))
