import logging
import asyncio
from bot.database.mongo import db
from bot.utils.parser import get_metadata

logger = logging.getLogger(__name__)

async def index_channel(userbot, chat_id, progress_msg=None):
    """
    Indexes all messages in a channel using the userbot.
    """
    try:
        latest_id = await db.get_latest_indexed_id(chat_id)
        count = 0

        async for message in userbot.get_chat_history(chat_id, offset_id=latest_id, reverse=True):
            if message.video or message.document or message.audio or message.animation:
                file_obj = message.video or message.document or message.audio or message.animation
                filename = getattr(file_obj, "file_name", "Unknown")
                caption = message.caption or ""

                # Enhanced metadata extraction
                season, episode, quality, title = get_metadata(caption, filename)

                index_data = {
                    "chat_id": chat_id,
                    "message_id": message.id,
                    "title": title,
                    "season": season,
                    "episode": episode,
                    "quality": quality,
                    "filename": filename,
                    "caption": caption
                }
                await db.add_index(index_data)
                count += 1

                if count % 100 == 0 and progress_msg:
                    try:
                        await progress_msg.edit_text(f"Indexing in progress...\nMessages processed: {count}")
                    except:
                        pass

        return count
    except Exception as e:
        logger.error(f"Error indexing channel {chat_id}: {e}")
        return -1
