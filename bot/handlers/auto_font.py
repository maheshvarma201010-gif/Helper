import logging
from pyrogram import Client, filters, enums
from bot.database.mongo import db
from bot.utils.stylizer import stylize_text
from bot.utils.replacer import render_message_to_html, replace_in_buttons

logger = logging.getLogger(__name__)

@Client.on_message(filters.channel & ~filters.service)
async def auto_font_handler(client, message):
    """
    Automatically stylizes new posts in channels that have a default font set.
    """
    channel_id = message.chat.id
    font_style = await db.get_channel_font(channel_id)

    if not font_style or font_style == "normal":
        return

    # Don't re-stylize if it looks like it was already handled or edited
    if message.edit_date:
        return

    try:
        current_html = ""
        if message.text:
            current_html = render_message_to_html(message.text, message.entities)
        elif message.caption:
            current_html = render_message_to_html(message.caption, message.caption_entities)

        if not current_html:
            return

        new_html = stylize_text(current_html, font_style)

        new_reply_markup = None
        if message.reply_markup:
            new_reply_markup = replace_in_buttons(message.reply_markup, "", "", stylize_font=font_style)

        if new_html != current_html or (message.reply_markup and new_reply_markup != message.reply_markup):
            if message.text:
                await client.edit_message_text(channel_id, message.id, new_html, parse_mode=enums.ParseMode.HTML, reply_markup=new_reply_markup)
            else:
                await client.edit_message_caption(channel_id, message.id, new_html, parse_mode=enums.ParseMode.HTML, reply_markup=new_reply_markup)

    except Exception as e:
        logger.error(f"Auto font error in channel {channel_id}: {e}")
