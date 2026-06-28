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

# Cache for user clients and media groups
user_clients = {}
media_group_cache = {}

async def get_user_client(user_id):
    if user_id in user_clients:
        client, last_time = user_clients[user_id]
        user_clients[user_id] = (client, time.time())
        return client

    session_string = await db.get_session(user_id)
    if not session_string:
        return None

    try:
        client = Client(
            f"user_{user_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=session_string,
            in_memory=True
        )
        await client.start()
        user_clients[user_id] = (client, time.time())
        return client
    except Exception as e:
        logger.error(f"Failed to start user client {user_id}: {e}")
        return None

async def cleanup_user_clients():
    while True:
        await asyncio.sleep(600)
        now = time.time()
        for user_id, (client, last_activity) in list(user_clients.items()):
            if now - last_activity > 1800:
                try: await client.stop()
                except: pass
                del user_clients[user_id]

@Client.on_message(filters.command("forward") & filters.private)
async def forward_command(client, message):
    user_id = message.from_user.id
    await db.reset_user(user_id)
    if not await db.get_session(user_id):
        return await message.reply_text("❌ Please save your string session first using /ss")

    await db.update_user_state(user_id, "fwd_start_link")
    await message.reply_text("🔗 **Forwarding Setup**\n\nPlease send the **First Message Link**.")

@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client, message):
    user_id = message.from_user.id
    await db.update_user_state(user_id, None)
    await db.users.update_one({"user_id": user_id}, {"$unset": {"temp_btn_wiz": "", "temp_dm_links": "", "temp_manual": ""}})
    await message.reply_text("✅ Current operation cancelled.")

@Client.on_message(filters.command("stop") & filters.private)
async def stop_command(client, message):
    user_id = message.from_user.id
    active_jobs = await db.forward_jobs.find({"user_id": user_id, "status": "running"}).to_list(length=None)
    if not active_jobs:
        return await message.reply_text("❌ No active forwarding jobs found.")

    for job in active_jobs:
        await db.update_forward_job(job["job_id"], {"status": "stopped"})

    await message.reply_text(f"🛑 Stopped {len(active_jobs)} active job(s).")

@Client.on_message(filters.private & filters.text, group=8)
async def handle_forward_input(client, message, override_text=None):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)
    if not state:
        if not override_text:
            message.continue_propagation()
        return

    text = override_text if override_text else message.text.strip()

    if not override_text and text.startswith("/"):
        if text in ["/cancel", "/stop"]:
            return # Handled by specific command handlers
        # Other commands might be intended to break state?
        # But for now we only care about cancel/stop.
        if state not in ["fwd_filter", "btn_wiz_count"]: # skip and last are valid in these states
             message.continue_propagation()
             return

    if state == "fwd_start_link":
        chat_id, first_id, _ = parse_message_link(text)
        if not chat_id: return await message.reply_text("❌ Invalid link.")
        await db.update_replace_data(user_id, {"source_chat": chat_id, "source_input": text, "start_id": first_id})
        await db.update_user_state(user_id, "fwd_end_link")
        await message.reply_text("✅ Start link saved.\n\nNow send the **Last Message Link**.")

    elif state == "fwd_end_link":
        data = await db.get_replace_data(user_id)
        chat_id, last_id, _ = parse_message_link(text)
        if not chat_id or chat_id != data.get("source_chat"):
             return await message.reply_text("❌ Link must be from the same channel.")
        await db.update_replace_data(user_id, {"end_id": last_id})
        await db.update_user_state(user_id, "fwd_target")
        await message.reply_text("✅ End link saved.\n\nNow send the **Target Channel ID/Username/Link**.")

    elif state == "fwd_target":
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e:
            return await message.reply_text(f"❌ Could not resolve target: {e}")
        await db.update_replace_data(user_id, {"target_chat": target_id, "target_input": text, "target_title": target_chat.title})
        await db.update_user_state(user_id, "fwd_filter")
        await message.reply_text("🔍 **Caption Filter**\n\nSend text to filter or /skip.")

    elif state == "fwd_filter":
        filter_text = None if text == "/skip" else text
        await db.update_replace_data(user_id, {"filter": filter_text})
        await db.update_user_state(user_id, "fwd_mode_choice")
        buttons = [[InlineKeyboardButton("🔍 Trace", callback_data="fwd_mode:trace"),
                    InlineKeyboardButton("🏁 Finish", callback_data="fwd_mode:finish")]]
        await message.reply_text("⚙️ **Select Mode:**", reply_markup=InlineKeyboardMarkup(buttons))

    elif state.startswith("dm_auto_url:"):
        _, msg_id, index = state.split(":")
        index = int(index)
        if not text.startswith("http"): return await message.reply_text("❌ Invalid URL.")
        config = await db.get_button_config(user_id)
        await db.users.update_one({"user_id": user_id}, {"$push": {"temp_dm_links": {"name": config["names"][index], "url": text}}})
        if index + 1 < len(config["names"]):
            await db.update_user_state(user_id, f"dm_auto_url:{msg_id}:{index + 1}")
            await message.reply_text(f"🔗 URL for **{config['names'][index + 1]}**:")
        else:
            await db.update_user_state(user_id, f"dm_target:{msg_id}")
            await message.reply_text("✅ Target Channel ID/Username:")

    elif state.startswith("dm_target:"):
        msg_id = int(state.split(":")[1])
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e: return await message.reply_text(f"❌ Error: {e}")
        user_data = await db.get_user(user_id)
        temp_links = user_data.get("temp_dm_links", [])
        buttons = []
        rows = (await db.get_button_config(user_id)).get("rows", 1)
        for i in range(0, len(temp_links), rows):
            row = []
            for btn in temp_links[i:i+rows]:
                row.append(InlineKeyboardButton(btn["name"], url=btn["url"]))
            buttons.append(row)
        user_client = await get_user_client(user_id)
        if not user_client:
            return await message.reply_text("❌ Failed to start your session client. Please check your /ss string.")

        bot_me = await client.get_me()
        try:
            await user_client.copy_message(target_id, bot_me.id, msg_id, reply_markup=InlineKeyboardMarkup(buttons))
            await message.reply_text("✅ Forwarded!")
        except Exception as e:
            logger.error(f"Interactive forward failed: {e}")
            await message.reply_text(f"❌ Failed: {e}")
        await db.update_user_state(user_id, None)
        await db.users.update_one({"user_id": user_id}, {"$unset": {"temp_dm_links": ""}})

    elif state.startswith("dm_manual_count:"):
        msg_id = state.split(":")[1]
        if text == "/last":
            user_data = await db.get_user(user_id)
            last_cfg = user_data.get("last_btn_config")
            if not last_cfg: return await message.reply_text("❌ No last configuration found.")
            await db.users.update_one({"user_id": user_id}, {"$set": {"temp_manual": {"btns": last_cfg["btns"], "rows": last_cfg["rows"]}}})
            await db.update_user_state(user_id, f"dm_manual_target:{msg_id}")
            return await message.reply_text("🎯 **Reusing last buttons.**\n\nSend **Target Destination** (ID/Username/Link).")

        if not text.isdigit(): return await message.reply_text("❌ Enter a number.")
        count = int(text)
        if count <= 0 or count > 20: return await message.reply_text("❌ Range: 1-20.")
        await db.users.update_one({"user_id": user_id}, {"$set": {"temp_manual": {"count": count, "btns": []}}})
        await db.update_user_state(user_id, f"dm_manual_btn:{msg_id}:0")
        await message.reply_text("✏️ Enter **Button 1 Name | Link**\nExample: `Google | https://google.com`")

    elif state.startswith("dm_manual_btn:"):
        _, msg_id, index = state.split(":")
        index = int(index)
        if " | " not in text: return await message.reply_text("❌ Format: `Name | Link`")
        name, url = [x.strip() for x in text.split(" | ", 1)]
        if not url.startswith(("http", "t.me/")): return await message.reply_text("❌ Invalid URL.")

        user_data = await db.get_user(user_id)
        manual_data = user_data.get("temp_manual", {})
        manual_data["btns"].append({"name": name, "url": url})
        await db.users.update_one({"user_id": user_id}, {"$set": {"temp_manual": manual_data}})

        if index + 1 < manual_data["count"]:
            await db.update_user_state(user_id, f"dm_manual_btn:{msg_id}:{index + 1}")
            await message.reply_text(f"✏️ Enter **Button {index + 2} Name | Link**:")
        else:
            await db.update_user_state(user_id, f"dm_manual_rows:{msg_id}")
            await message.reply_text("🔢 How many **buttons per row**?")

    elif state.startswith("dm_manual_rows:"):
        msg_id = state.split(":")[1]
        if not text.isdigit(): return await message.reply_text("❌ Enter a number.")
        rows = int(text)

        user_data = await db.get_user(user_id)
        manual_data = user_data.get("temp_manual", {})
        manual_data["rows"] = rows

        # Save as last config
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "temp_manual": manual_data,
            "last_btn_config": {"btns": manual_data["btns"], "rows": rows}
        }})

        await db.update_user_state(user_id, f"dm_manual_target:{msg_id}")
        await message.reply_text("✅ Config saved. Send **Target Channel ID/Username**.")

    elif state.startswith("dm_manual_target:"):
        msg_id = int(state.split(":")[1])
        try:
            target_chat = await resolve_chat(client, text)
            target_id = target_chat.id
        except Exception as e: return await message.reply_text(f"❌ Error: {e}")

        user_data = await db.get_user(user_id)
        manual_data = user_data.get("temp_manual", {})
        btns = manual_data.get("btns", [])
        rows = manual_data.get("rows", 1)

        buttons = []
        for i in range(0, len(btns), rows):
            row = []
            for b in btns[i:i+rows]:
                row.append(InlineKeyboardButton(b["name"], url=b["url"]))
            buttons.append(row)

        user_client = await get_user_client(user_id)
        if not user_client:
            return await message.reply_text("❌ Failed to start your session client. Please check your /ss string.")

        bot_me = await client.get_me()
        try:
            await user_client.copy_message(target_id, bot_me.id, msg_id, reply_markup=InlineKeyboardMarkup(buttons))
            await message.reply_text("✅ Forwarded (Manual)!")
        except Exception as e:
            logger.error(f"Manual interactive forward failed: {e}")
            await message.reply_text(f"❌ Failed: {e}")

        await db.update_user_state(user_id, None)
        await db.users.update_one({"user_id": user_id}, {"$unset": {"temp_manual": ""}})

    else:
        message.continue_propagation()

@Client.on_callback_query(filters.regex(r"^fwd_mode:(.+)"))
async def fwd_mode_callback(client, callback_query):
    mode = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    data = await db.get_replace_data(user_id)
    job_id = str(uuid.uuid4())
    await db.update_replace_data(user_id, {"job_id": job_id, "mode": mode})
    await db.update_user_state(user_id, None)
    summary = f"📋 **Summary**\n• Source: `{data['source_chat']}`\n• Range: `{data['start_id']}-{data['end_id']}`\n• Mode: `{mode}`"
    buttons = [[InlineKeyboardButton("🚀 Start", callback_data=f"start_fwd:{job_id}")]]
    await callback_query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_message(filters.private & (filters.photo | filters.video | filters.document | filters.animation | filters.audio | filters.voice | filters.sticker | filters.text) & ~filters.command(["start", "forward", "ss", "auto", "scrab", "stats", "tedit", "cancel", "stop", "login", "logout", "forwardstop"]), group=9)
async def handle_dm_media(client, message):
    user_id = message.from_user.id
    if await db.get_user_state(user_id): return

    if not await db.get_session(user_id):
        return await message.reply_text("❌ Please save your string session first using /ss before using interactive forwarding.")

    # Handle Media Groups (Albums) - only prompt once
    if message.media_group_id:
        if message.media_group_id in media_group_cache:
            return
        media_group_cache[message.media_group_id] = time.time()
        # Cleanup old cache entries periodically
        if len(media_group_cache) > 100:
            now = time.time()
            for mg_id, ts in list(media_group_cache.items()):
                if now - ts > 60: del media_group_cache[mg_id]

    # Check for Forward Tag
    is_forwarded = bool(message.forward_from or message.forward_from_chat or message.forward_sender_name)

    buttons = [
        [InlineKeyboardButton("🤖 Auto Mode", callback_data=f"dm_mode:auto:{message.id}"),
         InlineKeyboardButton("🛠 Manual Mode", callback_data=f"dm_mode:manual:{message.id}")]
    ]

    text = "🎯 **Forwarded Post Detected**" if is_forwarded else "📝 **New Post Detected**"
    text += "\n\nChoose your button attachment mode:"

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^dm_mode:(.+):(.+)"))
async def dm_mode_callback(client, callback_query):
    mode, msg_id = callback_query.matches[0].group(1), callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id

    if mode == "auto":
        config = await db.get_button_config(user_id)
        if not config or not config.get("names"):
            return await callback_query.answer("❌ No Auto buttons configured! Use /auto first.", show_alert=True)

        await db.users.update_one({"user_id": user_id}, {"$set": {"temp_dm_links": []}})
        await db.update_user_state(user_id, f"dm_auto_url:{msg_id}:0")
        await callback_query.message.edit_text(f"🤖 **Auto Mode**\n\n🔗 Please send the URL for: **{config['names'][0]}**")
    else:
        await db.update_user_state(user_id, f"dm_manual_count:{msg_id}")
        await callback_query.message.edit_text("🛠 **Manual Mode**\n\n🔢 How many buttons do you want to add?")

@Client.on_callback_query(filters.regex(r"^start_fwd:(.+)"))
async def start_fwd_callback(client, callback_query):
    job_id = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    data = await db.get_replace_data(user_id)
    job_data = {
        "job_id": job_id, "user_id": user_id, "source_chat": data["source_chat"],
        "source_input": data.get("source_input"), "target_chat": data["target_chat"],
        "target_input": data.get("target_input"), "filter": data.get("filter"),
        "start_id": min(data["start_id"], data["end_id"]), "end_id": max(data["start_id"], data["end_id"]),
        "current_id": min(data["start_id"], data["end_id"]), "status": "running",
        "success": 0, "failed": 0, "total": abs(data["end_id"] - data["start_id"]) + 1,
        "mode": data.get("mode"), "message_queue": [], "timestamp": time.time()
    }
    await db.add_forward_job(job_data)
    await forward_queue.put(job_id)
    await callback_query.answer("Started!")
    await show_forward_status(client, callback_query.message, job_id)

def get_progress_bar(percentage):
    c = int(percentage / 10)
    return "▰" * c + "▱" * (10 - c)

async def show_forward_status(client, message, job_id):
    job = await db.get_forward_job(job_id)
    if not job: return
    processed = job["success"] + job["failed"]
    percentage = (processed / job["total"] * 100) if job["total"] > 0 else 0
    text = (f"📊 **Status**\n• Status: `{job['status']}`\n"
            f"• Progress: `{get_progress_bar(percentage)}` `{percentage:.1f}%`\n"
            f"• Success: `{job['success']}` | Failed: `{job['failed']}`\n"
            f"• Total: `{job['total']}` | Queue: `{len(job['message_queue'])}`")
    buttons = [[InlineKeyboardButton("🛑 Stop", callback_data=f"fwd_ctrl:stop:{job_id}")]]
    try: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except: pass

@Client.on_callback_query(filters.regex(r"^fwd_ctrl:(.+):(.+)"))
async def fwd_ctrl_callback(client, callback_query):
    action, job_id = callback_query.matches[0].group(1), callback_query.matches[0].group(2)
    if action == "stop": await db.update_forward_job(job_id, {"status": "stopped"})
    await show_forward_status(client, callback_query.message, job_id)

async def forward_worker(client):
    while True:
        job_id = await forward_queue.get()
        try:
            job = await db.get_forward_job(job_id)
            if not job or job["status"] != "running": continue
            user_client = await get_user_client(job["user_id"])
            if not user_client:
                await db.update_forward_job(job_id, {"status": "failed"})
                continue

            async def process_msg(msg_id):
                try:
                    msg = await user_client.get_messages(job["source_chat"], msg_id)
                    if not msg or msg.empty: return False, 1

                    # Filtering logic
                    if job.get("filter"):
                        f = job["filter"].lower()
                        text_to_check = [msg.text or "", msg.caption or ""]
                        if msg.document: text_to_check.append(msg.document.file_name or "")
                        if msg.video: text_to_check.append(msg.video.file_name or "")
                        if msg.audio: text_to_check.append(msg.audio.file_name or "")

                        content = " ".join(text_to_check).lower()
                        if f not in content:
                            count = len(await user_client.get_media_group(job["source_chat"], msg_id)) if msg.media_group_id else 1
                            return False, count

                    if msg.media_group_id:
                        copied = await user_client.copy_media_group(job["target_chat"], job["source_chat"], msg_id)
                        return True, len(copied)
                    else:
                        await user_client.copy_message(job["target_chat"], job["source_chat"], msg_id)
                        return True, 1
                except errors.FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    return await process_msg(msg_id)
                except Exception as e:
                    logger.error(f"Worker Error: {e}")
                    # Attempt to join if access error
                    if "USER_NOT_PARTICIPANT" in str(e) or "CHANNEL_PRIVATE" in str(e):
                        try: await user_client.join_chat(job.get("source_input") or job["source_chat"])
                        except: pass
                    return False, 1

            # Range
            while job["current_id"] <= job["end_id"]:
                job = await db.get_forward_job(job_id)
                if not job or job["status"] != "running": break
                success, count = await process_msg(job["current_id"])
                if success: await db.update_forward_job(job_id, {"success": job["success"] + count, "current_id": job["current_id"] + count})
                else: await db.update_forward_job(job_id, {"failed": job["failed"] + count, "current_id": job["current_id"] + count})
                await asyncio.sleep(1)

            # Queue
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
        except Exception as e: logger.error(f"Worker task error: {e}")
        finally: forward_queue.task_done()

@Client.on_message(group=10)
async def trace_monitor(client, message):
    if not message.chat: return
    active_jobs = await db.forward_jobs.find({
        "source_chat": {"$in": [message.chat.id, f"@{message.chat.username}"]},
        "status": "running"
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
