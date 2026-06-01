import asyncio
import logging
from pyrogram import Client, filters, enums, errors
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.database.mongo import db
from bot.utils.stylizer import stylize_text, get_available_fonts
from bot.utils.helpers import resolve_chat
from bot.utils.replacer import render_message_to_html, replace_in_buttons
from bot.config import Config

logger = logging.getLogger(__name__)

# Font selection markup
def get_font_markup(action, channel_id=None):
    buttons = []
    fonts = get_available_fonts()
    # Chunk fonts into 2 per row
    for i in range(0, len(fonts), 2):
        row = []
        for font in fonts[i:i+2]:
            callback_data = f"font:{action}:{font}"
            if channel_id:
                callback_data += f":{channel_id}"
            row.append(InlineKeyboardButton(font.replace("_", " ").title(), callback_data=callback_data))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

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
        return await message.reply_text("Usage: `/font <channel_id/link>` (Applies font to existing messages)")

    query = message.command[1]
    try:
        chat = await resolve_chat(client, query)
        channel_id = chat.id
    except Exception as e:
        return await message.reply_text(f"❌ Error: {e}")

    await message.reply_text(
        f"Select a font style to apply to messages in `{chat.title}`:",
        reply_markup=get_font_markup("apply", channel_id)
    )

@Client.on_callback_query(filters.regex(r"^font:"))
async def font_callback(client: Client, callback: CallbackQuery):
    data = callback.data.split(":")
    action = data[1]
    font = data[2]
    channel_id = int(data[3]) if len(data) > 3 else None

    if action == "set":
        if font == "normal":
            await db.delete_channel_font(channel_id)
            await callback.edit_message_text(f"✅ Default font removed for channel `{channel_id}`.")
        else:
            await db.set_channel_font(channel_id, font)
            await callback.edit_message_text(f"✅ Default font set to `{font}` for channel `{channel_id}`.")

    elif action == "apply":
        await callback.edit_message_text(f"🚀 Starting font conversion to `{font}`. This may take a while...")
        asyncio.create_task(apply_font_task(client, callback.message, channel_id, font))

async def apply_font_task(client, status_msg, chat_id, font):
    worker = client.userbot or client
    count = 0

    try:
        # We need to find the range of messages.
        # For simplicity in this tool, we'll fetch the last 200 messages.
        # In a real scenario, we might want to allow specifying a range.
        async for msg in worker.get_chat_history(chat_id, limit=200):
            if not msg or msg.empty: continue

            # Stylize caption or text
            current_html = ""
            if msg.text:
                current_html = render_message_to_html(msg.text, msg.entities)
            elif msg.caption:
                current_html = render_message_to_html(msg.caption, msg.caption_entities)

            if not current_html:
                continue

            new_html = stylize_text(current_html, font)

            new_reply_markup = None
            if msg.reply_markup:
                 # Optionally stylize button text too
                 new_reply_markup = replace_in_buttons(msg.reply_markup, "", "", stylize_font=font)

            if new_html != current_html or (msg.reply_markup and new_reply_markup != msg.reply_markup):
                try:
                    if msg.text:
                        await worker.edit_message_text(chat_id, msg.id, new_html, parse_mode=enums.ParseMode.HTML, reply_markup=new_reply_markup)
                    else:
                        await worker.edit_message_caption(chat_id, msg.id, new_html, parse_mode=enums.ParseMode.HTML, reply_markup=new_reply_markup)
                    count += 1
                    await asyncio.sleep(0.5)
                except errors.FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    logger.error(f"Failed to apply font to {msg.id}: {e}")

        await status_msg.edit_text(f"✅ Font conversion complete! Modified {count} messages.")
    except Exception as e:
        logger.error(f"Font task failed: {e}")
        await status_msg.edit_text(f"❌ Font task failed: {e}")
