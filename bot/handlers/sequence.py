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
        "🚀 **Sequencer Mode Activated**\n\n"
        "Please send/forward all videos or files you want to sort.\n"
        "I will organize them by:\n"
        "1️⃣ **Season**\n"
        "2️⃣ **Quality** (480p, 720p, etc.)\n"
        "3️⃣ **Episode**\n\n"
        "✨ **Total Collected:** `0` files\n\n"
        "➡️ Send /sort when you are ready to finish."
    )
    # Save the status message ID in sequence job to update it later
    # Using a dedicated field in sequences instead of reusing replace_data
    await db.sequences.update_one({"user_id": user_id}, {"$set": {"status_msg_id": status.id}}, upsert=True)

@Client.on_message(filters.private & ~filters.command(["sort", "sequence", "start", "replace", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "redirect", "font", "fontchannel", "replace_domain", "tedit", "tedit_status", "tedit_stop", "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview"]), group=5)
async def collect_files(client, message: Message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        message.continue_propagation()
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
            data = await db.sequences.find_one({"user_id": user_id})
            if data and "status_msg_id" in data:
                try:
                    await client.edit_message_text(
                        chat_id=user_id,
                        message_id=data["status_msg_id"],
                        text=f"🔄 **File Collection In Progress**\n\n"
                             f"Organizing your media library...\n\n"
                             f"✨ **Total Collected:** `{count}` files\n\n"
                             f"➡️ Send more files or /sort to finalize the order."
                    )
                except Exception:
                    pass
    else:
        # If user sends text that isn't a command, remind them
        if message.text:
            await message.reply_text("❌ Please send a valid **Video** or **Document** file, or use /sort to finish.")

@Client.on_message(filters.command("sort") & filters.private)
async def sort_command(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "collecting_files":
        return await message.reply_text("⚠️ You are not in collection mode. Start with /sequence first.")

    files = await db.get_sequence_files(user_id)
    if not files:
        await message.reply_text("⚠️ No files were collected. Aborting process.")
        await db.update_user_state(user_id, None)
        return

    # Ask for sort type
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [
        [InlineKeyboardButton("Season -> Episode -> Quality", callback_data="seq_sort:standard")],
        [InlineKeyboardButton("Episode -> Season -> Quality", callback_data="seq_sort:episode_wise")],
        [InlineKeyboardButton("Quality -> Season -> Episode", callback_data="seq_sort:quality_wise")],
        [InlineKeyboardButton("Alphabetical (Filename)", callback_data="seq_sort:filename_wise")],
        [InlineKeyboardButton("Season Only", callback_data="seq_sort:season_only"),
         InlineKeyboardButton("Episode Only", callback_data="seq_sort:episode_only")],
        [InlineKeyboardButton("Reverse (Recently Added)", callback_data="seq_sort:reverse")]
    ]
    await message.reply_text("🎨 **Choose Sorting Method:**\nHow should I organize your files?", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^seq_sort:(.+)"))
async def handle_sort_callback(client, callback_query):
    user_id = callback_query.from_user.id
    sort_type = callback_query.matches[0].group(1)

    files = await db.get_sequence_files(user_id)
    if not files:
        return await callback_query.answer("No files found to sort.", show_alert=True)

    await callback_query.message.edit_text(f"🚀 **Sorting Method: `{sort_type}`**\n\nPreparing delivery...")

    # Sort files
    try:
        sorted_list = sort_files(files, sort_type=sort_type)
    except Exception as e:
        logger.error(f"Sorting error: {e}")
        return await callback_query.message.edit_text(f"❌ **Sorting Engine Error:**\n`{e}`")

    await callback_query.message.edit_text(f"📦 **Delivering {len(sorted_list)} files...**")

    count = 0
    for file_info in sorted_list:
        try:
            # Use copy_message to preserve original caption, entities and media layout
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=user_id,
                message_id=file_info["message_id"]
            )
            count += 1
            await asyncio.sleep(0.3)
        except errors.FloodWait as e:
            await asyncio.sleep(e.value + 1)
            # Retry
            await client.copy_message(user_id, user_id, file_info["message_id"])
            count += 1
        except Exception as e:
            logger.warning(f"Failed to send file {file_info.get('message_id')}: {e}")

    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, None)

    await callback_query.message.reply_text(
        f"🏁 **Sequencing Finished!**\n\n"
        f"✅ **Total Files Organized:** `{count}`\n"
        f"📁 **Status:** `Success` 🧬"
    )
