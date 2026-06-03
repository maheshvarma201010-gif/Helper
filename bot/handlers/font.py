import asyncio
import logging
from pyrogram import Client, filters, enums, errors
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.database.mongo import db
from bot.utils.stylizer import stylize_text
from bot.utils.helpers import resolve_chat, parse_message_link, get_font_markup
from bot.utils.replacer import render_message_to_html, replace_in_buttons
from bot.config import Config

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("fontchannel") & filters.user(Config.ADMINS))
async def font_channel_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/fontchannel <channel_id/link>`")

    query = message.command[1]
    try:
        chat = await resolve_chat(client, query)
        channel_id = chat.id
    except Exception as e:
        return await message.reply_text(f"❌ Error: {e}")

    await message.reply_text(
        f"Select a default font style for `{chat.title}`:",
        reply_markup=get_font_markup("set", channel_id)
    )

@Client.on_message(filters.command("font") & filters.user(Config.ADMINS))
async def font_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/font <message_link>` (e.g., .../10-20)")

    link = message.command[1]
    chat_id, first_id, last_id = parse_message_link(link)

    if not chat_id:
        # Try if it's just a channel ID/username
        try:
            chat = await resolve_chat(client, link)
            chat_id = chat.id
            first_id = 0 # Scan history
            last_id = 0
        except Exception as e:
            return await message.reply_text(f"❌ Error: Invalid link or channel: {e}")

    await message.reply_text(
        f"Select a font style to apply to messages in `{chat_id}` (Range: {first_id}-{last_id}):",
        reply_markup=get_font_markup(f"apply:{first_id}:{last_id}", chat_id)
    )

@Client.on_callback_query(filters.regex(r"^font:(set|apply):"))
async def font_callback(client: Client, callback: CallbackQuery):
    await callback.answer() # Stop loading spinner
    data = callback.data.split(":")

    def parse_id(val):
        try:
            return int(val)
        except (ValueError, TypeError):
            return val

    # Check for apply with range: font:apply:first:last:font_style:channel_id
    if data[1] == "apply" and len(data) >= 6:
        first_id = int(data[2])
        last_id = int(data[3])
        font = data[4]
        channel_id = parse_id(data[5])
        await callback.edit_message_text(f"🚀 Starting font conversion to `{font}` for {channel_id} (Range: {first_id}-{last_id})...")
        asyncio.create_task(apply_font_task(client, callback.message, channel_id, font, first_id, last_id))
        return

    # Standard set or apply: font:action:font_style:channel_id
    action = data[1]
    font = data[2]
    channel_id = parse_id(data[3]) if len(data) > 3 else None

    if action == "set":
        if font == "normal":
            await db.delete_channel_font(channel_id)
            await callback.edit_message_text(f"✅ Default font removed for channel `{channel_id}`.")
        else:
            await db.set_channel_font(channel_id, font)
            await callback.edit_message_text(f"✅ Default font set to `{font}` for channel `{channel_id}`.")

    elif action == "apply":
        await callback.edit_message_text(f"🚀 Starting font conversion to `{font}` for {channel_id}. This may take a while...")
        asyncio.create_task(apply_font_task(client, callback.message, channel_id, font))

async def apply_font_task(client, status_msg, chat_id, font, first_id=0, last_id=0):
    worker = client
    count = 0
    processed = 0

    # Accurate total for progress
    if first_id > 0 and last_id > 0:
        total = last_id - first_id + 1
        # Start message
        await status_msg.edit_text(f"🚀 **Starting range conversion...**\nRange: `{first_id}-{last_id}`\nFont: `{font}`")
    else:
        total = 200
        await status_msg.edit_text(f"🚀 **Starting history conversion...**\nLimit: `200` messages\nFont: `{font}`")

    try:
        if first_id > 0 and last_id > 0:
            # Iterate through range in batches of 100
            for i in range(first_id, last_id + 1, 100):
                batch_limit = min(i + 100, last_id + 1)
                batch_ids = list(range(i, batch_limit))

                try:
                    messages = await worker.get_messages(chat_id, batch_ids)
                except Exception as e:
                    logger.error(f"Error fetching batch {i}-{batch_limit}: {e}")
                    processed += len(batch_ids)
                    continue

                if not isinstance(messages, list): messages = [messages]

                for msg in messages:
                    processed += 1
                    if not msg or msg.empty: continue

                    # Target both text and captions (files)
                    if await process_msg_font(worker, chat_id, msg, font):
                        count += 1
                        await asyncio.sleep(0.05) # Optimized sleep

                    if processed % 50 == 0 or processed == total:
                        try:
                            await status_msg.edit_text(
                                f"⏳ **Font conversion in progress...**\n\n"
                                f"✅ Processed: `{processed}/{total}`\n"
                                f"✨ Modified: `{count}`\n"
                                f"🎯 Font: `{font}`"
                            )
                        except: pass
        else:
            # Last 200 messages
            async for msg in worker.get_chat_history(chat_id, limit=200):
                processed += 1
                if not msg or msg.empty: continue
                if await process_msg_font(worker, chat_id, msg, font):
                    count += 1
                    await asyncio.sleep(0.1)

                if processed % 50 == 0:
                    try:
                        await status_msg.edit_text(f"⏳ Font conversion in progress...\n\nProcessed: `{processed}/{total}`\nModified: `{count}`")
                    except: pass

        await status_msg.edit_text(f"✅ Font conversion complete!\n\nTotal Processed: `{processed}`\nModified: `{count}`")
    except Exception as e:
        logger.error(f"Font task failed: {e}")
        await status_msg.edit_text(f"❌ Font task failed: {e}")

async def process_msg_font(worker, chat_id, msg, font):
    # Stylize caption or text
    current_html = ""
    if msg.text:
        current_html = render_message_to_html(msg.text, msg.entities)
    elif msg.caption:
        current_html = render_message_to_html(msg.caption, msg.caption_entities)

    if not current_html:
        return False

    new_html = stylize_text(current_html, font, is_button=False)

    new_reply_markup = None
    if msg.reply_markup:
         new_reply_markup = replace_in_buttons(msg.reply_markup, "", "", stylize_font=font)

    if new_html != current_html or (msg.reply_markup and new_reply_markup != msg.reply_markup):
        try:
            if msg.text:
                await worker.edit_message_text(chat_id, msg.id, new_html, parse_mode=enums.ParseMode.HTML, reply_markup=new_reply_markup)
            else:
                # Preserve media caption position (above/below)
                invert = getattr(msg, "invert_media", False)
                await worker.edit_message_caption(
                    chat_id, msg.id, new_html,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=new_reply_markup,
                    invert_media=invert
                )
            return True
        except errors.FloodWait as e:
            await asyncio.sleep(e.value + 1)
            # Retry once
            return await process_msg_font(worker, chat_id, msg, font)
        except Exception as e:
            logger.error(f"Failed to apply font to {msg.id}: {e}")
    return False
