import asyncio
import logging
import re
from pyrogram import Client, filters, errors, enums
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.replacer import replace_in_html, replace_in_buttons, render_message_to_html
from bot.config import Config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("replace") & filters.private)
async def replace_command(client, message):
    user_id = message.from_user.id
    await db.clear_replace_data(user_id)
    await db.update_user_state(user_id, "awaiting_first_link")
    await message.reply_text("Send FIRST message link.")

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "sequence", "replace", "sort", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "font", "fontchannel", "replace_domain", "b", "tedit", "tedit_status", "tedit_stop", "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview"]), group=3)
async def handle_replace_workflow(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("awaiting_") or state.startswith("awaiting_domain_"):
        message.continue_propagation()
        return

    if state == "awaiting_first_link":
        chat_id, msg_id = parse_message_link(message.text)
        if not chat_id:
            return await message.reply_text("❌ Invalid link. Please send a valid message link.")

        if Config.REPLACE_TEXT_CHANNELS and chat_id not in Config.REPLACE_TEXT_CHANNELS:
            return await message.reply_text("❌ This channel is not authorized for text replacement.")

        await db.update_replace_data(user_id, {"chat_id": chat_id, "first_msg_id": msg_id})
        await db.update_user_state(user_id, "awaiting_last_link")
        await message.reply_text("Send LAST message link.")

    elif state == "awaiting_last_link":
        replace_data = await db.get_replace_data(user_id)
        if not replace_data:
            await db.update_user_state(user_id, None)
            return await message.reply_text("Session expired. Please start over with /replace")

        chat_id, msg_id = parse_message_link(message.text)
        if not chat_id or chat_id != replace_data.get("chat_id"):
            return await message.reply_text("❌ Invalid link or link from different chat.")

        await db.update_replace_data(user_id, {"last_msg_id": msg_id})
        await db.update_user_state(user_id, "awaiting_old_text")
        await message.reply_text("Which text/link/username should be replaced?")

    elif state == "awaiting_old_text":
        await db.update_replace_data(user_id, {"old_text": message.text})
        await db.update_user_state(user_id, "awaiting_new_text")
        await message.reply_text("Replace with?")

    elif state == "awaiting_new_text":
        await db.update_replace_data(user_id, {"new_text": message.text})
        await start_replacement(client, message, user_id)

async def start_replacement(client, message, user_id):
    data = await db.get_replace_data(user_id)
    if not data or "chat_id" not in data:
        await message.reply_text("❌ Incomplete data. Please start over.")
        await db.clear_replace_data(user_id)
        await db.update_user_state(user_id, None)
        return

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

    await message.reply_text(f"✅ Starting replacement in `{chat.title}`\n🔄 `{old_text}` -> `{new_text}`...")

    count = 0
    for i in range(first_id, last_id + 1, 100):
        batch_ids = list(range(i, min(i + 100, last_id + 1)))
        try:
            messages = await worker.get_messages(chat_id, batch_ids)
            if not isinstance(messages, list): messages = [messages]

            for msg in messages:
                if not msg or msg.empty: continue

                # Get HTML with entities preserved
                if msg.text:
                    current_html = render_message_to_html(msg.text, msg.entities)
                elif msg.caption:
                    current_html = render_message_to_html(msg.caption, msg.caption_entities)
                else:
                    current_html = ""

                # Perform Smart Replacement
                new_html = replace_in_html(current_html, old_text, new_text)

                new_reply_markup = None
                if msg.reply_markup:
                    new_reply_markup = replace_in_buttons(msg.reply_markup, old_text, new_text)

                # Check if anything actually changed (HTML or Buttons)
                if new_html != current_html or (msg.reply_markup and new_reply_markup != msg.reply_markup):
                    # Retry logic
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
                            count += 1
                            await asyncio.sleep(0.5)
                            break
                        except errors.FloodWait as e:
                            await asyncio.sleep(e.value + 1)
                        except errors.MessageNotModified:
                            break
                        except Exception as e:
                            logger.error(f"Failed to edit {msg.id}: {e}")
                            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Batch failed: {e}")

    await message.reply_text(f"🏁 Replacement complete! Modified {count} messages.")
    await db.clear_replace_data(user_id)
    await db.update_user_state(user_id, None)
