from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from pyrogram import enums
import html
import re

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
                props = {k: v for k, v in button.__dict__.items() if k not in ['text', 'url', 'callback_data'] and not k.startswith('_')}
                new_row.append(InlineKeyboardButton(text=new_btn_text, **props))
        new_rows.append(new_row)

    return InlineKeyboardMarkup(new_rows)

def render_message_to_html(text, entities):
    """
    Renders a message with entities into an HTML string.
    Correctly handles nested entities by sorting by length and offset.
    """
    if not entities:
        return html.escape(text)

    # Sort entities: primary by offset (ascending), secondary by length (descending)
    # This ensures parent tags wrap children correctly
    sorted_entities = sorted(entities, key=lambda e: (e.offset, -e.length))

    # We use a recursive approach or a tag-insertion approach.
    # For Telegram, a tag-insertion approach with reverse iteration is safer.

    # But wait, a much easier way for Pyrogram 2.x to get HTML:
    # Actually, Pyrogram Message objects HAVE entities, and we can use them.
    # If the standard .html doesn't work, we'll use this manual builder:

    # We'll use a simple character-by-character builder with tag stacks.
    tags = []
    for entity in entities:
        tags.append((entity.offset, 'start', entity))
        tags.append((entity.offset + entity.length, 'end', entity))

    # Sort tags:
    # 1. offset ASC
    # 2. If same offset, 'end' before 'start'
    # 3. If both 'end', the one that started LATER must end FIRST (shorter length)
    # 4. If both 'start', the one that ends LATER must start FIRST (longer length)

    def tag_priority(tag):
        offset, type, entity = tag
        if type == 'end':
            # At same offset, end the one that started MOST RECENTLY first
            return (offset, 0, -entity.offset)
        else:
            # At same offset, start the LONGEST one first
            return (offset, 1, -entity.length)

    tags.sort(key=tag_priority)

    result = ""
    last_offset = 0
    for offset, type, entity in tags:
        result += html.escape(text[last_offset:offset])
        if type == 'start':
            if entity.type == enums.MessageEntityType.BOLD: result += "<b>"
            elif entity.type == enums.MessageEntityType.ITALIC: result += "<i>"
            elif entity.type == enums.MessageEntityType.UNDERLINE: result += "<u>"
            elif entity.type == enums.MessageEntityType.STRIKETHROUGH: result += "<s>"
            elif entity.type == enums.MessageEntityType.CODE: result += "<code>"
            elif entity.type == enums.MessageEntityType.PRE: result += "<pre>"
            elif entity.type == enums.MessageEntityType.TEXT_LINK: result += f'<a href="{entity.url}">'
            elif entity.type == enums.MessageEntityType.URL: result += f'<a href="{html.escape(text[entity.offset:entity.offset+entity.length])}">'
        else:
            if entity.type == enums.MessageEntityType.BOLD: result += "</b>"
            elif entity.type == enums.MessageEntityType.ITALIC: result += "</i>"
            elif entity.type == enums.MessageEntityType.UNDERLINE: result += "</u>"
            elif entity.type == enums.MessageEntityType.STRIKETHROUGH: result += "</s>"
            elif entity.type == enums.MessageEntityType.CODE: result += "</code>"
            elif entity.type == enums.MessageEntityType.PRE: result += "</pre>"
            elif entity.type in [enums.MessageEntityType.TEXT_LINK, enums.MessageEntityType.URL]: result += "</a>"
        last_offset = offset
    result += html.escape(text[last_offset:])
    return result

def replace_in_html(html_text, old_text, new_text):
    """
    Replaces text in HTML-formatted string.
    Includes smart protocol-agnostic matching for URLs.
    """
    if not html_text:
        return html_text

    # 1. Exact match
    res = html_text.replace(old_text, new_text)
    if res != html_text:
        return res

    # 2. Protocol-agnostic match (e.g., matching http:// even if query was https://)
    clean_old = re.sub(r'^https?://', '', old_text)
    if clean_old != old_text:
        # Match both http and https versions of the domain/path
        pattern = re.compile(r'https?://' + re.escape(clean_old), re.IGNORECASE)
        res = pattern.sub(new_text, html_text)
        if res != html_text:
            return res

    # 3. Final fallback: Case-insensitive regex match
    pattern = re.compile(re.escape(old_text), re.IGNORECASE)
    return pattern.sub(new_text, html_text)
