import asyncio
import logging
import time
from pyrogram import Client, filters, errors, enums
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.replacer import replace_in_html, replace_in_buttons, render_message_to_html
from bot.utils.stylizer import destylize
from bot.config import Config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("replace_domain") & filters.user(Config.OWNER_ID))
async def replace_domain_command(client, message):
    if await db.is_domain_job_running():
        return await message.reply_text("❌ A domain replacement task is already running. Use /cancel_replace to stop it.")

    user_id = message.from_user.id
    await db.clear_domain_data(user_id)
    await db.update_user_state(user_id, "awaiting_domain_first_link")
    await message.reply_text("🔗 **Send FIRST Message Link:**")

@Client.on_message(filters.command("cancel_replace") & filters.user(Config.OWNER_ID))
async def cancel_replace_command(client, message):
    user_id = message.from_user.id
    await db.set_domain_job_status(False)
    await db.update_user_state(user_id, None)
    await message.reply_text("🛑 **Domain replacement task cancelled.**")

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "sequence", "replace", "sort", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "font", "fontchannel", "replace_domain", "cancel_replace", "b", "tedit", "tedit_status", "tedit_stop", "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview"]), group=4)
async def handle_domain_workflow(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("awaiting_domain_"):
        message.continue_propagation()
        return

    if state == "awaiting_domain_first_link":
        chat_id, msg_id, _ = parse_message_link(message.text)
        if not chat_id:
            return await message.reply_text("❌ Invalid link. Send a valid message link.")
        await db.update_domain_data(user_id, {"chat_id": chat_id, "first_msg_id": msg_id})
        await db.update_user_state(user_id, "awaiting_domain_last_link")
        await message.reply_text("🔗 **Send LAST Message Link:**")

    elif state == "awaiting_domain_last_link":
        data = await db.get_domain_data(user_id)
        chat_id, msg_id, _ = parse_message_link(message.text)
        if not chat_id or chat_id != data.get("chat_id"):
            return await message.reply_text("❌ Link must be from the same channel.")
        await db.update_domain_data(user_id, {"last_msg_id": msg_id})
        await db.update_user_state(user_id, "awaiting_old_domain")
        await message.reply_text("🔍 **Enter OLD Domain/Text to replace:**\nExample: `https://old.com` or `old.com`")

    elif state == "awaiting_old_domain":
        # Destylize domain search term
        old_text = destylize(message.text)
        await db.update_domain_data(user_id, {"old_text": old_text})
        await db.update_user_state(user_id, "awaiting_new_domain")
        await message.reply_text("🔄 **Enter NEW Domain/Text:**\nExample: `https://new.com` or `new.com`")

    elif state == "awaiting_new_domain":
        await db.update_domain_data(user_id, {"new_text": message.text})
        await start_domain_replacement(client, message, user_id)

async def start_domain_replacement(client, message, user_id):
    data = await db.get_domain_data(user_id)
    if not data: return

    chat_id = data["chat_id"]
    first_id = min(data["first_msg_id"], data["last_msg_id"])
    last_id = max(data["first_msg_id"], data["last_msg_id"])
    old_text = data["old_text"]
    new_text = data["new_text"]

    worker = client
    try:
        chat = await resolve_chat(worker, chat_id)
        chat_id = chat.id
    except Exception as e:
        return await message.reply_text(f"❌ Error resolving chat: {e}")

    await db.set_domain_job_status(True)
    progress_msg = await message.reply_text("🔄 **Domain Replacement Running...**\n\nStarting scans...")

    start_time = time.time()
    total = last_id - first_id + 1
    edited = 0
    skipped = 0
    failed = 0
    processed = 0

    for i in range(first_id, last_id + 1, 100):
        if not await db.is_domain_job_running(): break # Cancellation check

        batch_ids = list(range(i, min(i + 100, last_id + 1)))
        try:
            messages = await worker.get_messages(chat_id, batch_ids)
            if not isinstance(messages, list): messages = [messages]

            for msg in messages:
                if not await db.is_domain_job_running(): break
                processed += 1

                if not msg or msg.empty or (not msg.text and not msg.caption):
                    skipped += 1
                    continue

                # Prepare HTML content
                if msg.text:
                    current_html = render_message_to_html(msg.text, msg.entities)
                else:
                    current_html = render_message_to_html(msg.caption, msg.caption_entities)

                # Check for match (case-insensitive)
                if old_text.lower() not in current_html.lower() and not (msg.reply_markup and old_text.lower() in str(msg.reply_markup).lower()):
                    skipped += 1
                    continue

                # Perform replacement
                new_html = replace_in_html(current_html, old_text, new_text)
                new_reply_markup = None
                if msg.reply_markup:
                    new_reply_markup = replace_in_buttons(msg.reply_markup, old_text, new_text)

                if new_html != current_html or (msg.reply_markup and new_reply_markup != msg.reply_markup):
                    # Retry logic
                    success = False
                    for attempt in range(3):
                        try:
                            if msg.text:
                                await worker.edit_message_text(chat_id, msg.id, new_html, parse_mode=enums.ParseMode.HTML, reply_markup=new_reply_markup)
                            else:
                                # Preserve media caption position (above/below)
                                invert = getattr(msg, "invert_media", False)
                                await worker.edit_message_caption(
                                    chat_id, msg.id, new_html,
                                    parse_mode=enums.ParseMode.HTML,
                                    reply_markup=new_reply_markup,
                                    invert_media=invert
                                )
                            edited += 1
                            success = True
                            await asyncio.sleep(0.5)
                            break
                        except errors.FloodWait as e:
                            await asyncio.sleep(e.value + 1)
                        except errors.MessageNotModified:
                            skipped += 1
                            success = True
                            break
                        except Exception as e:
                            logger.error(f"Edit failed msg {msg.id} (attempt {attempt+1}): {e}")
                            await asyncio.sleep(1)

                    if not success: failed += 1
                else:
                    skipped += 1

                # Progress update every 20 messages
                if processed % 20 == 0:
                    try:
                        await progress_msg.edit_text(
                            f"🔄 **Domain Replacement Running...**\n\n"
                            f"Processed: {processed}/{total}\n"
                            f"Edited: {edited}\n"
                            f"Skipped: {skipped}\n"
                            f"Failed: {failed}"
                        )
                    except: pass

        except Exception as e:
            logger.error(f"Batch processing error in {chat_id}: {e}")
            failed += len(batch_ids)

    duration = time.time() - start_time
    minutes, seconds = divmod(int(duration), 60)
    time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    await db.set_domain_job_status(False)
    await db.update_user_state(user_id, None)

    completion_text = (
        f"✅ **Domain Replacement Completed**\n\n"
        f"📊 **Statistics**\n\n"
        f"Total Messages: {total}\n"
        f"Edited: {edited}\n"
        f"Skipped: {skipped}\n"
        f"Failed: {failed}\n\n"
        f"Old Domain:\n`{old_text}`\n\n"
        f"New Domain:\n`{new_text}`\n\n"
        f"Time Taken: {time_str}"
    )
    await message.reply_text(completion_text)
    try: await progress_msg.delete()
    except: pass
