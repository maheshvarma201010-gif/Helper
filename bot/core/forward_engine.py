import asyncio
from typing import List, Dict, Any
from pyrogram import Client, errors
from pyrogram.types import Message
from bot.core.progress import ProgressTracker
from bot.core.logger import logger
from bot.utils.constants import MessageTypes

class ForwardEngine:
    BATCH_SIZE = 100

    def __init__(self, client: Client, bot_client: Client):
        self.client = client
        self.bot_client = bot_client
        self.is_running = True

    async def start_forward(
        self,
        source_chat: Any,
        target_chat: Any,
        start_id: int,
        end_id: int,
        filters: List[str],
        status_message: Message
    ):
        total = end_id - start_id + 1
        tracker = ProgressTracker(total)

        logger.info(f"Starting ULTRA SPEED forward from {start_id} to {end_id}")

        current_id = start_id
        while current_id <= end_id:
            if not self.is_running:
                break

            batch_end = min(current_id + self.BATCH_SIZE - 1, end_id)
            message_ids = list(range(current_id, batch_end + 1))

            try:
                # ULTRA SPEED: Fetch batch
                messages = await self.client.get_messages(source_chat, message_ids)

                if not isinstance(messages, list):
                    messages = [messages]

                # Maintain strict order: messages are returned in the order of IDs provided
                for msg in messages:
                    if not self.is_running:
                        break

                    if not msg or msg.empty:
                        tracker.increment_skipped()
                    elif self._matches_filters(msg, filters):
                        # Attempt forward
                        try:
                            await self._copy_message(msg, target_chat)
                            tracker.increment_success()
                        except errors.FloodWait as e:
                            logger.warning(f"FloodWait during copy: {e.value} seconds. Retrying...")
                            await asyncio.sleep(e.value)
                            # Retry current message once
                            try:
                                await self._copy_message(msg, target_chat)
                                tracker.increment_success()
                            except:
                                tracker.increment_failed()
                        except Exception as e:
                            logger.error(f"Failed to copy message {msg.id}: {e}")
                            tracker.increment_failed()
                    else:
                        tracker.increment_skipped()

                    # Minimal delay for high speed (adjust as needed)
                    await asyncio.sleep(0.05)

                current_id = batch_end + 1

                if tracker.should_update():
                    await self._update_status(status_message, tracker, batch_end)

            except errors.FloodWait as e:
                logger.warning(f"FloodWait during batch fetch: {e.value} seconds. Retrying batch.")
                await asyncio.sleep(e.value)
                # Retry same current_id
                continue
            except Exception as e:
                logger.error(f"Error fetching batch {current_id}-{batch_end}: {e}")
                # If batch fails, skip to next batch to avoid getting stuck
                current_id = batch_end + 1

        await self._update_status(status_message, tracker, end_id, final=True)
        logger.info("Forwarding complete.")

    async def _copy_message(self, msg: Message, target_chat: Any):
        # We use copy_message to avoid forwarded tag
        await msg.copy(target_chat)

    def _matches_filters(self, msg: Message, filters: List[str]) -> bool:
        if not filters or "🌐 All Media" in filters:
            return True

        if msg.photo and MessageTypes.PHOTO in filters: return True
        if msg.document and MessageTypes.DOCUMENT in filters: return True
        if msg.video and MessageTypes.VIDEO in filters: return True
        if msg.audio and MessageTypes.AUDIO in filters: return True
        if msg.voice and MessageTypes.VOICE in filters: return True
        if msg.animation and MessageTypes.ANIMATION in filters: return True
        if msg.sticker and MessageTypes.STICKER in filters: return True
        if msg.poll and MessageTypes.POLL in filters: return True
        if msg.location and MessageTypes.LOCATION in filters: return True
        if msg.contact and MessageTypes.CONTACT in filters: return True
        if msg.video_note and MessageTypes.VIDEO_NOTE in filters: return True
        if msg.media_group_id and MessageTypes.ALBUM in filters: return True

        # Text and Link filters
        if msg.text or msg.caption:
            text = msg.text or msg.caption
            if MessageTypes.TEXT in filters:
                return True
            if MessageTypes.LINK in filters:
                # Basic link check
                if "http" in text or "t.me" in text:
                    return True

        return False

    def stop(self):
        self.is_running = False

    async def _update_status(self, status_msg: Message, tracker: ProgressTracker, current_id: int, final: bool = False):
        status = "✅ **Completed**" if final else "⚡ **ULTRA SPEED Forwarding...**"
        if not self.is_running and not final:
            status = "🛑 **Stopped**"

        text = (
            f"{status}\n\n"
            f"📊 **Progress:** {tracker.get_progress_bar()}\n"
            f"🔢 **Total:** {tracker.total}\n"
            f"✅ **Success:** {tracker.success}\n"
            f"❌ **Failed:** {tracker.failed}\n"
            f"⏭ **Skipped:** {tracker.skipped}\n"
            f"⚡ **Speed:** {tracker.get_speed()}\n"
            f"⏳ **ETA:** {tracker.get_eta()}\n"
            f"📍 **Current ID:** `{current_id}`"
        )
        try:
            await status_msg.edit_text(text)
        except errors.FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass
