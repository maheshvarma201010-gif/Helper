import os
import logging
from pyrogram import Client, filters
from bot.handlers.link import process_media_message

logger = logging.getLogger(__name__)

@Client.on_message(filters.private & (filters.video | filters.document))
async def media_auto_handler(client, message):
    """
    Auto-detects forwarded or sent videos and MKV/MP4 document files,
    downloads them, extracts audio tracks, and provides Watch & Download links.
    """
    # Ignore messages that are commands
    if message.text and message.text.startswith("/"):
        return

    media = message.video or message.document
    if not media:
        return

    # Check extension / mime type
    file_name = getattr(media, "file_name", None) or ""
    file_ext = os.path.splitext(file_name)[1].lower() if file_name else ""
    mime_type = getattr(media, "mime_type", "") or ""

    valid_exts = [".mkv", ".mp4", ".avi", ".mov", ".webm"]

    # If it's a video or a document matching video formats
    if message.video or (message.document and (file_ext in valid_exts or mime_type.startswith("video/"))):
        await process_media_message(client, message, message)
