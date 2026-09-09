import os
import uuid
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import Config
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.media import extract_audio_tracks, format_audio_tracks_summary

logger = logging.getLogger(__name__)

async def process_media_message(client, message, target_msg):
    """
    Core function that downloads media from target_msg, extracts audio tracks,
    stores metadata in MongoDB, and replies with Watch & Download links.
    """
    media = target_msg.video or target_msg.document
    if not media:
        await message.reply_text("❌ The specified message does not contain a supported video or document.")
        return

    # Validate file extension/mime type if document
    file_name = getattr(media, "file_name", None) or f"video_{target_msg.id}.mp4"
    file_ext = os.path.splitext(file_name)[1].lower()
    mime_type = getattr(media, "mime_type", "") or ""

    valid_exts = [".mkv", ".mp4", ".avi", ".mov", ".webm"]
    if target_msg.document and not (file_ext in valid_exts or mime_type.startswith("video/")):
        await message.reply_text("❌ Unsupported file format. Please send an MKV or MP4 video/document.")
        return

    status_msg = await message.reply_text("⏳ Processing media... Please wait.")

    try:
        chat_id = target_msg.chat.id
        msg_id = target_msg.id

        # Check if already processed
        existing = await db.get_media_file_by_message(chat_id, msg_id)
        if existing and os.path.exists(existing.get("file_path", "")):
            file_id = existing["file_id"]
            tracks = existing.get("audio_tracks", [])
        else:
            file_id = str(uuid.uuid4())
            file_dir = os.path.join("downloads", file_id)
            os.makedirs(file_dir, exist_ok=True)

            await status_msg.edit_text("📥 Downloading video file from Telegram...")
            file_path = os.path.join(file_dir, file_name)

            await client.download_media(
                message=target_msg,
                file_name=file_path
            )

            await status_msg.edit_text("🎵 Extracting audio tracks using FFmpeg...")
            tracks = await extract_audio_tracks(file_path, file_dir)

            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else getattr(media, "file_size", 0)

            file_data = {
                "file_id": file_id,
                "file_name": file_name,
                "file_path": file_path,
                "file_dir": file_dir,
                "file_size": file_size,
                "mime_type": mime_type or "video/mp4",
                "chat_id": chat_id,
                "message_id": msg_id,
                "audio_tracks": tracks
            }

            await db.add_media_file(file_data)

        base_url = Config.BASE_URL.rstrip('/')
        watch_url = f"{base_url}/watch/{file_id}"
        download_url = f"{base_url}/download/{file_id}"

        tracks_summary = format_audio_tracks_summary(tracks)

        caption = (
            f"🎬 **File Link Generated!**\n\n"
            f"📁 **Filename:** `{file_name}`\n"
            f"📊 **Size:** `{round(getattr(media, 'file_size', 0) / (1024 * 1024), 2)} MB`\n\n"
            f"{tracks_summary}\n\n"
            f"🔗 Click below to watch online with audio switcher or download directly:"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍿 Watch Online", url=watch_url),
                InlineKeyboardButton("📥 Direct Download", url=download_url)
            ]
        ])

        await status_msg.edit_text(caption, reply_markup=buttons)

    except Exception as e:
        logger.exception(f"Error processing media message: {e}")
        await status_msg.edit_text(f"❌ Failed to process media: {e}")

@Client.on_message(filters.command("link") & (filters.private | filters.group))
async def link_command(client, message):
    """
    /link command handler.
    Can be used as reply to a video/document or with a Telegram message link.
    """
    # 1. If replied to a message
    if message.reply_to_message:
        target_msg = message.reply_to_message
        if target_msg.video or target_msg.document:
            await process_media_message(client, message, target_msg)
            return
        else:
            await message.reply_text("❌ The replied message does not contain a video or document.")
            return

    # 2. If message contains arguments (e.g., /link https://t.me/c/12345/67)
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        link = args[1].strip()
        chat_id, first_id, _ = parse_message_link(link)

        if not chat_id or not first_id:
            await message.reply_text("❌ Invalid Telegram message link provided.")
            return

        try:
            chat = await resolve_chat(client, chat_id)
            target_msg = await client.get_messages(chat.id, first_id)
            if target_msg and (target_msg.video or target_msg.document):
                await process_media_message(client, message, target_msg)
                return
            else:
                await message.reply_text("❌ No video or document found at that link.")
                return
        except Exception as e:
            logger.exception(f"Error fetching message from link: {e}")
            await message.reply_text(f"❌ Could not access message link: {e}")
            return

    # 3. No reply and no arguments
    usage_text = (
        "🔗 **How to use `/link`:**\n\n"
        "1. **Reply `/link`** to any video or MKV/MP4 document message.\n"
        "2. **Or send:** `/link <telegram_message_link>`\n"
        "   Example: `/link https://t.me/c/123456789/10`"
    )
    await message.reply_text(usage_text)
