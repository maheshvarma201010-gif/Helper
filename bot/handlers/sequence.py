import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.database.mongo import db
from bot.utils.parser import get_metadata
from bot.utils.sorter import sort_files

@Client.on_message(filters.command("sequence") & filters.private)
async def sequence_command(client, message):
    user_id = message.from_user.id
    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, "collecting_files")
    await message.reply_text("Send all files/videos. When finished send /done")

@Client.on_message(filters.private & ~filters.command(["done", "sequence", "start", "replace"]))
async def collect_files(client, message: Message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return

    if message.video or message.document or message.audio or message.animation:
        file_obj = message.video or message.document or message.audio or message.animation
        filename = getattr(file_obj, "file_name", "Unknown")
        caption = message.caption or ""

        # Extract metadata
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

@Client.on_message(filters.command("done") & filters.private)
async def done_command(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return

    files = await db.get_sequence_files(user_id)
    if not files:
        await message.reply_text("No files collected.")
        await db.update_user_state(user_id, None)
        return

    await message.reply_text(f"Collected {len(files)} files. Sorting and sending...")

    # Sort files
    sorted_list = sort_files(files)

    # Send files back
    for file_info in sorted_list:
        try:
            # We use copy_message to preserve everything
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=message.chat.id,
                message_id=file_info["message_id"]
            )
            await asyncio.sleep(0.5) # Avoid flood
        except Exception as e:
            await message.reply_text(f"Error sending file: {e}")

    # Cleanup
    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, None)
    await message.reply_text("Sequencing complete!")
