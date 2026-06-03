import asyncio
import time
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import Message
from bot.database.mongo import db
from bot.utils.parser import get_metadata
from bot.utils.sorter import sort_files
from bot.utils.helpers import get_font_markup
from bot.utils.stylizer import stylize_text
from bot.utils.replacer import render_message_to_html

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
    await db.update_replace_data(user_id, {"status_msg_id": status.id})

@Client.on_message(filters.private & ~filters.command(["sort", "sequence", "start", "replace", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "redirect", "font", "fontchannel", "replace_domain"]))
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

    await message.reply_text(
        f"📊 **Collected {len(files)} files.**\nSelect a font style for the captions before I deliver them:",
        reply_markup=get_font_markup("seq_sort")
    )

@Client.on_callback_query(filters.regex(r"^font:seq_sort:"))
async def sequence_sort_callback(client: Client, callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    font = callback.data.split(":")[2]

    files = await db.get_sequence_files(user_id)
    if not files:
        return await callback.message.edit_text("⚠️ Collection data lost. Please start over.")

    await callback.message.edit_text(f"🚀 **Applying font `{font}` and sorting...**")

    # Sort files: Season -> Quality -> Episode
    try:
        sorted_list = sort_files(files)
    except Exception as e:
        logger.error(f"Sorting error: {e}")
        return await callback.message.edit_text(f"❌ **Sorting Engine Error:**\n`{e}`")

    await callback.message.edit_text(f"📦 **Delivering {len(sorted_list)} files with stylized captions...**")

    count = 0
    for file_info in sorted_list:
        try:
            # Re-fetch the message to ensure we have current entities
            msg = await client.get_messages(callback.message.chat.id, file_info["message_id"])

            caption = msg.caption or ""
            entities = msg.caption_entities

            if caption:
                # Render to HTML and then stylize
                html_caption = render_message_to_html(caption, entities)
                new_caption = stylize_text(html_caption, font, is_button=False)

                # Send the media with the NEW stylized caption
                # Preserve media caption position (above/below)
                invert = getattr(msg, "invert_media", False)
                if msg.video:
                    await client.send_video(callback.message.chat.id, msg.video.file_id, caption=new_caption, parse_mode=enums.ParseMode.HTML, invert_media=invert)
                elif msg.document:
                    await client.send_document(callback.message.chat.id, msg.document.file_id, caption=new_caption, parse_mode=enums.ParseMode.HTML, invert_media=invert)
                elif msg.audio:
                    await client.send_audio(callback.message.chat.id, msg.audio.file_id, caption=new_caption, parse_mode=enums.ParseMode.HTML, invert_media=invert)
                elif msg.animation:
                    await client.send_animation(callback.message.chat.id, msg.animation.file_id, caption=new_caption, parse_mode=enums.ParseMode.HTML, invert_media=invert)
            else:
                # No caption, just copy
                await client.copy_message(callback.message.chat.id, callback.message.chat.id, file_info["message_id"])

            count += 1
            await asyncio.sleep(0.3)
        except errors.FloodWait as e:
            await asyncio.sleep(e.value + 1)
            # Simple retry
            await client.copy_message(callback.message.chat.id, callback.message.chat.id, file_info["message_id"])
            count += 1
        except Exception as e:
            logger.warning(f"Failed to send file {file_info.get('message_id')}: {e}")

    await db.clear_sequence_files(user_id)
    await db.update_user_state(user_id, None)

    await callback.message.reply_text(
        f"🏁 **Sequencing Finished!**\n\n"
        f"✅ **Total Files Organized:** `{count}`\n"
        f"📁 **Font Applied:** `{font}`\n"
        f"📁 **Status:** `Success` 🧬"
    )
