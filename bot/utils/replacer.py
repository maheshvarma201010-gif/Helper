from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from pyrogram import enums
import html
import re
from bot.utils.stylizer import destylize

def replace_text(text, old_text, new_text):
    """
    Robust string replacement that handles stylized text.
    Applies all replacement types sequentially to ensure coverage.
    """
    if not text:
        return text

    # 1. Exact & Case-insensitive match on original text
    pattern = re.compile(re.escape(old_text), re.IGNORECASE)
    text = pattern.sub(new_text, text)

    # 2. Match on destylized version
    # If the destylized version contains the old_text (case-insensitive),
    # we replace in the destylized version.
    clean_text = destylize(text)
    if old_text.lower() in clean_text.lower():
        # This replaces stylized characters with new_text
        text = pattern.sub(new_text, clean_text)

    return text

def replace_in_buttons(reply_markup, old_text, new_text, stylize_font=None):
    """Correctly replaces text and URLs in InlineKeyboardMarkup buttons."""
    if not reply_markup or not isinstance(reply_markup, InlineKeyboardMarkup):
        return reply_markup

    from bot.utils.stylizer import stylize_text

    new_rows = []
    for row in reply_markup.inline_keyboard:
        new_row = []
        for button in row:
            new_btn_text = replace_text(button.text, old_text, new_text)
            if stylize_font:
                new_btn_text = stylize_text(new_btn_text, stylize_font, is_button=True)

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
        # We need to escape special characters even if there are no entities
        # to ensure it's valid HTML for the bot API
        return html.escape(text).replace("&amp;amp;", "&amp;") # Prevent double escape if already escaped

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
            elif entity.type == enums.MessageEntityType.MENTION: result += f'<a href="https://t.me/{text[entity.offset+1:entity.offset+entity.length]}">'
            elif entity.type == enums.MessageEntityType.HASHTAG: result += f'<a href="https://t.me/share/url?url={html.escape(text[entity.offset:entity.offset+entity.length])}">'
            elif entity.type == enums.MessageEntityType.CASHTAG: result += f'<a href="https://t.me/share/url?url={html.escape(text[entity.offset:entity.offset+entity.length])}">'
        else:
            if entity.type == enums.MessageEntityType.BOLD: result += "</b>"
            elif entity.type == enums.MessageEntityType.ITALIC: result += "</i>"
            elif entity.type == enums.MessageEntityType.UNDERLINE: result += "</u>"
            elif entity.type == enums.MessageEntityType.STRIKETHROUGH: result += "</s>"
            elif entity.type == enums.MessageEntityType.CODE: result += "</code>"
            elif entity.type == enums.MessageEntityType.PRE: result += "</pre>"
            elif entity.type in [enums.MessageEntityType.TEXT_LINK, enums.MessageEntityType.URL, enums.MessageEntityType.MENTION, enums.MessageEntityType.HASHTAG, enums.MessageEntityType.CASHTAG]: result += "</a>"
        last_offset = offset
    result += html.escape(text[last_offset:])
    return result

def replace_in_html(html_text, old_text, new_text):
    """
    Replaces text in HTML-formatted string.
    Handles stylized text, hyperlinked text, and protocol-agnostic matching.
    """
    if not html_text:
        return html_text

    # Standardize old_text by destylizing it first
    old_text = destylize(old_text)

    # Apply all replacement passes sequentially

    # 1. Protocol-agnostic match for URLs (e.g., matching http:// even if query was https://)
    clean_old = re.sub(r'^https?://', '', old_text)
    if clean_old != old_text:
        pattern = re.compile(r'https?://' + re.escape(clean_old), re.IGNORECASE)
        html_text = pattern.sub(new_text, html_text)

    # 2. Standard Case-insensitive regex match
    pattern = re.compile(re.escape(old_text), re.IGNORECASE)
    html_text = pattern.sub(new_text, html_text)

    # 3. Destylize & Hyperlink check: if the content contains stylized versions or hidden links
    clean_html = destylize(html_text)
    if old_text.lower() in clean_html.lower() or 'href="' in html_text:
        # Split by tags and handle text parts
        tag_pattern = r'(<[^>]+>)'
        parts = re.split(tag_pattern, html_text)
        new_parts = []
        for p in parts:
            if not p: continue
            if p.startswith('<') and p.endswith('>'):
                # Handle URLs inside tags like <a href="...">
                if 'href="' in p:
                    url_match = re.search(r'href="([^"]+)"', p)
                    if url_match:
                        full_tag = p
                        url_content = url_match.group(1)
                        # Avoid infinite recursion by checking if replacement is needed
                        if old_text.lower() in destylize(url_content).lower():
                             # Use simple replace for internal URL to avoid complex nesting
                             new_url = replace_text(url_content, old_text, new_text)
                             p = full_tag.replace(f'href="{url_content}"', f'href="{new_url}"')
                new_parts.append(p)
            else:
                # Replace in the text part using robust replace_text
                new_parts.append(replace_text(p, old_text, new_text))

        html_text = "".join(new_parts)

    return html_text
