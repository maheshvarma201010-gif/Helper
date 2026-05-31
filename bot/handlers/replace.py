import asyncio
import logging
from pyrogram import Client, filters, errors
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link
from bot.utils.replacer import replace_text, replace_in_buttons
from bot.config import Config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("replace") & filters.private)
async def replace_command(client, message):
    user_id = message.from_user.id
    await db.clear_replace_data(user_id)
    await db.update_user_state(user_id, "awaiting_first_link")
    await message.reply_text("Send FIRST message link.")

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "sequence", "replace", "done"]))
async def handle_replace_workflow(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("awaiting_"):
        return

    if state == "awaiting_first_link":
        chat_id, msg_id = parse_message_link(message.text)
        if not chat_id:
            return await message.reply_text("Invalid link. Please send a valid message link.")

        # Channel restriction check
        if Config.REPLACE_TEXT_CHANNELS and chat_id not in Config.REPLACE_TEXT_CHANNELS:
            return await message.reply_text("This channel is not authorized for text replacement.")

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
            return await message.reply_text("Invalid link or link from different chat. Please send a valid message link from the same chat.")

        await db.update_replace_data(user_id, {"last_msg_id": msg_id})
        await db.update_user_state(user_id, "awaiting_old_text")
        await message.reply_text("Which text should be replaced?")

    elif state == "awaiting_old_text":
        await db.update_replace_data(user_id, {"old_text": message.text})
        await db.update_user_state(user_id, "awaiting_new_text")
        await message.reply_text("Replace with?")

    elif state == "awaiting_new_text":
        await db.update_replace_data(user_id, {"new_text": message.text})
        await start_replacement(client, message, user_id)

async def start_replacement(client, message, user_id):
    data = await db.get_replace_data(user_id)
    if not data or "chat_id" not in data or "first_msg_id" not in data or "last_msg_id" not in data or "old_text" not in data or "new_text" not in data:
        await message.reply_text("Incomplete data. Please start over with /replace")
        await db.clear_replace_data(user_id)
        await db.update_user_state(user_id, None)
        return

    chat_id = data["chat_id"]
    first_id = min(data["first_msg_id"], data["last_msg_id"])
    last_id = max(data["first_msg_id"], data["last_msg_id"])
    old_text = data["old_text"]
    new_text = data["new_text"]

    # Admin check - send test message
    try:
        test_msg = await client.send_message(chat_id, "⚙️ Verification: Bot is preparing for bulk replacement...")
        await test_msg.delete()
    except errors.ChatAdminRequired:
        return await message.reply_text("❌ Error: I am not an admin in that channel or I don't have permission to post/delete messages.")
    except Exception as e:
        return await message.reply_text(f"❌ Error verifying permissions: {e}")

    await message.reply_text(f"✅ Permissions verified. Starting replacement from {first_id} to {last_id} in {chat_id}...")

    count = 0
    # Process in batches of 100
    for i in range(first_id, last_id + 1, 100):
        batch_ids = list(range(i, min(i + 100, last_id + 1)))
        try:
            messages = await client.get_messages(chat_id, batch_ids)
            if not isinstance(messages, list):
                messages = [messages]

            for msg in messages:
                if not msg or msg.empty:
                    continue

                changed = False
                current_text = msg.text or msg.caption or ""

                if old_text in current_text:
                    new_msg_text = replace_text(current_text, old_text, new_text)
                    changed = True
                else:
                    new_msg_text = current_text

                new_reply_markup = None
                if msg.reply_markup:
                    new_reply_markup = replace_in_buttons(msg.reply_markup, old_text, new_text)
                    if new_reply_markup != msg.reply_markup:
                        changed = True

                if changed:
                    try:
                        if msg.text:
                            await client.edit_message_text(chat_id, msg.id, new_msg_text, reply_markup=new_reply_markup)
                        else:
                            await client.edit_message_caption(chat_id, msg.id, new_msg_text, reply_markup=new_reply_markup)
                        count += 1
                        await asyncio.sleep(1) # Base sleep
                    except errors.FloodWait as e:
                        logger.warning(f"FloodWait: {e.value} seconds")
                        await asyncio.sleep(e.value)
                        # Retry
                        if msg.text:
                            await client.edit_message_text(chat_id, msg.id, new_msg_text, reply_markup=new_reply_markup)
                        else:
                            await client.edit_message_caption(chat_id, msg.id, new_msg_text, reply_markup=new_reply_markup)
                        count += 1
                    except errors.MessageNotModified:
                        pass
                    except Exception as e:
                        logger.error(f"Failed to edit {msg.id}: {e}")
        except Exception as e:
             logger.error(f"Error processing batch starting at {i}: {e}")

    await message.reply_text(f"Replacement complete! Modified {count} messages.")
    await db.clear_replace_data(user_id)
    await db.update_user_state(user_id, None)
