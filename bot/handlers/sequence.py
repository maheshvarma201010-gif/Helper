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

    # Store message_id for progress updates
    status = await message.reply_text(
        "📥 **File Collection Started**\n\n"
        "Please send all videos/files you want to sequence.\n"
        "I will sort them by Season, Quality, and Episode.\n\n"
        "**Progress:** 0 files collected\n\n"
        "When finished, send /done"
    )
    # Save the status message ID in sequence job to update it later
    await db.update_replace_data(user_id, {"status_msg_id": status.id})

@Client.on_message(filters.private & ~filters.command(["done", "sequence", "start", "replace", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "redirect"]))
async def collect_files(client, message: Message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return

    if message.video or message.document or message.audio or message.animation:
        file_obj = message.video or message.document or message.audio or message.animation
        filename = getattr(file_obj, "file_name", "Unknown")
        caption = message.caption or ""

        # Metadata extraction
        season, episode, quality, title = get_metadata(caption, filename)

        file_data = {
            "message_id": message.id,
            "file_id": file_obj.file_id,
            "caption": caption,
            "filename": filename,
            "season": season,
            "episode": episode,
            "quality": quality,
            "timestamp": time.time()
        }
        await db.add_sequence_file(user_id, file_data)

        # Get count and update progress every 10 files
        files = await db.get_sequence_files(user_id)
        count = len(files)

        if count % 10 == 0:
            data = await db.get_replace_data(user_id)
            if data and "status_msg_id" in data:
                try:
                    await client.edit_message_text(
                        chat_id=user_id,
                        message_id=data["status_msg_id"],
                        text=f"📥 **File Collection In Progress**\n\n"
                             f"**Progress:** {count} files collected\n\n"
                             f"Send more files or /done to finish."
                    )
                except Exception:
                    pass
    else:
        await message.reply_text("Please send a valid video or document file.")

@Client.on_message(filters.command("done") & filters.private)
async def done_command(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return await message.reply_text("⚠️ You are not in collection mode. Start with /sequence first.")

    files = await db.get_sequence_files(user_id)
    if not files:
        await message.reply_text("⚠️ No files collected. Aborting.")
        await db.update_user_state(user_id, None)
        return

    status_msg = await message.reply_text(f"📊 Collected {len(files)} files. Sorting and sending back...")

    # Sort files: Season -> Quality -> Episode
    try:
        sorted_list = sort_files(files)
    except Exception as e:
        logger.error(f"Sorting error: {e}")
        return await status_msg.edit_text(f"❌ Sorting failed: {e}")

    count = 0
    for file_info in sorted_list:
        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=message.chat.id,
                message_id=file_info["message_id"]
            )
            count += 1
            await asyncio.sleep(0.5)
        except errors.FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception:
            pass

    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, None)
    await status_msg.edit_text(f"✅ **Sequencing Complete!**\nSent {count} files in sorted order.")
