import asyncio
import time
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import Message
from bot.database.mongo import db
from bot.utils.parser import get_metadata
from bot.utils.sorter import sort_files

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("sequence") & filters.private)
async def sequence_command(client, message):
    user_id = message.from_user.id
    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, "collecting_files")
    await message.reply_text(
        "📥 **File Collection Started**\n\n"
        "Please send all videos/files you want to sequence.\n"
        "I will sort them by Season, Quality, and Episode.\n\n"
        "When finished, send /done\n"
        "To abort, send /cancel"
    )

@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)
    if state:
        await db.update_user_state(user_id, None)
        await db.clear_sequence_files(user_id)
        await db.clear_replace_data(user_id)
        await message.reply_text("❌ Operation cancelled and temporary data cleared.")
    else:
        await message.reply_text("No active operation to cancel.")

@Client.on_message(filters.private & ~filters.command(["done", "sequence", "start", "replace", "search", "cancel", "setchannel", "setbot", "reindex", "verify"]))
async def collect_files(client, message: Message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return

    if message.video or message.document or message.audio or message.animation:
        file_obj = message.video or message.document or message.audio or message.animation
        filename = getattr(file_obj, "file_name", "Unknown")
        caption = message.caption or ""

        # Enhanced metadata extraction
        season, episode, quality, title = get_metadata(caption, filename)

        file_data = {
            "message_id": message.id,
            "file_id": file_obj.file_id,
            "caption": caption,
            "filename": filename,
            "season": season,
            "episode": episode,
            "quality": quality,
            "type": message.media.value,
            "timestamp": time.time()
        }
        await db.add_sequence_file(user_id, file_data)
        # We don't send a message for every file to avoid flood,
        # but we could add a reaction if supported by the bot API version
    else:
        await message.reply_text("Please send a valid video or document file.")

@Client.on_message(filters.command("done") & filters.private)
async def done_command(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return

    files = await db.get_sequence_files(user_id)
    if not files:
        await message.reply_text("⚠️ No files collected. Aborting.")
        await db.update_user_state(user_id, None)
        return

    status_msg = await message.reply_text(f"📊 Collected {len(files)} files. Sorting and sending back...")

    # Sort files using the strict priority: Season -> Quality -> Episode
    sorted_list = sort_files(files)

    count = 0
    for file_info in sorted_list:
        # Retry logic for sending
        for attempt in range(3):
            try:
                # Use copy_message to preserve File ID, Caption, and Filename exactly
                await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=message.chat.id,
                    message_id=file_info["message_id"]
                )
                count += 1
                await asyncio.sleep(0.5) # Anti-flood delay
                break
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logger.error(f"Error sending file {file_info['message_id']} on attempt {attempt+1}: {e}")
                await asyncio.sleep(2)

    # Cleanup
    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, None)
    await status_msg.edit_text(f"✅ **Sequencing Complete!**\nSent {count} files in sorted order.")
