from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from pyrogram import enums
import html

def replace_text(text, old_text, new_text):
    """Simple string replacement for text."""
    if not text:
        return text
    return text.replace(old_text, new_text)

def replace_in_buttons(reply_markup, old_text, new_text):
    """Correctly replaces text and URLs in InlineKeyboardMarkup buttons."""
    if not reply_markup or not isinstance(reply_markup, InlineKeyboardMarkup):
        return reply_markup

    new_rows = []
    for row in reply_markup.inline_keyboard:
        new_row = []
        for button in row:
            new_btn_text = replace_text(button.text, old_text, new_text)

            if button.url:
                new_url = replace_text(button.url, old_text, new_text)
                new_row.append(InlineKeyboardButton(text=new_btn_text, url=new_url))
            elif button.callback_data:
                new_cb_data = button.callback_data
                if isinstance(new_cb_data, str):
                    new_cb_data = replace_text(new_cb_data, old_text, new_text)
                new_row.append(InlineKeyboardButton(text=new_btn_text, callback_data=new_cb_data))
            else:
                # Reconstruct other buttons
                props = {k: v for k, v in button.__dict__.items() if k not in ['text', 'url', 'callback_data'] and not k.startswith('_')}
                new_row.append(InlineKeyboardButton(text=new_btn_text, **props))
        new_rows.append(new_row)

    return InlineKeyboardMarkup(new_rows)

def render_message_to_html(text, entities):
    """
    Renders a message with entities into an HTML string.
    """
    if not entities:
        return html.escape(text)

    # Sort entities by offset in reverse to avoid offset shifts
    sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)

    result = list(text)
    for entity in sorted_entities:
        start = entity.offset
        end = entity.offset + entity.length
        content = html.escape("".join(result[start:end]))

        tag_start = ""
        tag_end = ""

        if entity.type == enums.MessageEntityType.BOLD:
            tag_start, tag_end = "<b>", "</b>"
        elif entity.type == enums.MessageEntityType.ITALIC:
            tag_start, tag_end = "<i>", "</i>"
        elif entity.type == enums.MessageEntityType.UNDERLINE:
            tag_start, tag_end = "<u>", "</u>"
        elif entity.type == enums.MessageEntityType.STRIKETHROUGH:
            tag_start, tag_end = "<s>", "</s>"
        elif entity.type == enums.MessageEntityType.CODE:
            tag_start, tag_end = "<code>", "</code>"
        elif entity.type == enums.MessageEntityType.PRE:
            tag_start, tag_end = "<pre>", "</pre>"
        elif entity.type == enums.MessageEntityType.TEXT_LINK:
            tag_start, tag_end = f'<a href="{entity.url}">', "</a>"
        elif entity.type == enums.MessageEntityType.URL:
            # We don't necessarily need tags for raw URLs in HTML parse mode,
            # but we can wrap them in <a> if we want to be explicit.
            tag_start, tag_end = f'<a href="{content}">', "</a>"
        elif entity.type == enums.MessageEntityType.MENTION:
             tag_start, tag_end = f'<a href="https://t.me/{content[1:]}">', "</a>"

        if tag_start:
            result[start:end] = [tag_start + content + tag_end]

    return "".join(result)

def replace_in_html(html_text, old_text, new_text):
    """Replaces text in HTML-formatted string."""
    if not html_text:
        return html_text
    return html_text.replace(old_text, new_text)
