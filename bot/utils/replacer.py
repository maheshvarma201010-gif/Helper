from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from pyrogram import enums
import html
import re
from bot.utils.stylizer import destylize

def replace_text(text, old_text, new_text):
    """
    God Ultra Ultimate Robust string replacement.
    Handles stylized text, HTML entities, and Unicode mathematical blocks.
    """
    if not text:
        return text

    # 1. Standard Case-insensitive match on original text
    pattern = re.compile(re.escape(old_text), re.IGNORECASE)
    text = pattern.sub(new_text, text)

    # 2. Match on Destylized + Unescaped version
    # Handles: &#𝘅𝟮𝟳; -> &#x27; -> '
    # Handles: 𝗴𝗼𝗼𝗴𝗹𝗲.𝗰𝗼𝗺 -> google.com
    clean = html.unescape(destylize(text))
    if old_text.lower() in clean.lower():
        # If found in clean version, we return the replaced clean version.
        # This satisfies "replace anywhere" even if it means losing original font
        # for that specific piece of text.
        text = pattern.sub(new_text, clean)

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
    God Ultra Ultimate Replaces text in HTML-formatted string.
    Handles stylized text, hyperlinked text, entities and protocol-agnostic matching.
    """
    if not html_text:
        return html_text

    # Standardize old_text by destylizing it first
    old_text = destylize(old_text)

    # Apply all replacement passes sequentially

    # 1. Protocol-agnostic match for URLs
    clean_old = re.sub(r'^https?://', '', old_text)
    if clean_old != old_text:
        pattern = re.compile(r'https?://' + re.escape(clean_old), re.IGNORECASE)
        html_text = pattern.sub(new_text, html_text)

    # 2. Standard Case-insensitive regex match
    pattern = re.compile(re.escape(old_text), re.IGNORECASE)
    html_text = pattern.sub(new_text, html_text)

    # 3. Deep Scan (Destylize, Unescape, Hyperlink target)
    # This pass ensures even complex hidden links and stylized entities are caught.
    tag_pattern = r'(<[^>]+>)'
    parts = re.split(tag_pattern, html_text)
    new_parts = []
    for p in parts:
        if not p: continue
        if p.startswith('<') and p.endswith('>'):
            # Handle hidden URLs in href attributes
            if 'href="' in p:
                url_match = re.search(r'href="([^"]+)"', p)
                if url_match:
                    full_tag = p
                    url_content = url_match.group(1)
                    # Check if URL content (unescaped/destylized) matches
                    clean_url = html.unescape(destylize(url_content))
                    if old_text.lower() in clean_url.lower():
                        # Replace in URL content
                        new_url = pattern.sub(new_text, clean_url)
                        p = full_tag.replace(f'href="{url_content}"', f'href="{new_url}"')
            new_parts.append(p)
        else:
            # Replace in text parts using God-mode replace_text
            new_parts.append(replace_text(p, old_text, new_text))

    return "".join(new_parts)
