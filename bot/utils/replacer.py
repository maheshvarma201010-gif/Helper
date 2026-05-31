from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
            # Replace in button text
            new_btn_text = replace_text(button.text, old_text, new_text)

            # Handle different button types
            if button.url:
                # Replace in button URL
                new_url = replace_text(button.url, old_text, new_text)
                new_row.append(InlineKeyboardButton(text=new_btn_text, url=new_url))
            elif button.callback_data:
                # Replace in callback data if it's a string
                new_cb_data = button.callback_data
                if isinstance(new_cb_data, str):
                    new_cb_data = replace_text(new_cb_data, old_text, new_text)
                new_row.append(InlineKeyboardButton(text=new_btn_text, callback_data=new_cb_data))
            else:
                # Other button types (switch_inline_query, etc.)
                new_row.append(InlineKeyboardButton(text=new_btn_text, **{k: v for k, v in button.__dict__.items() if k not in ['text', 'url', 'callback_data']}))
        new_rows.append(new_row)

    return InlineKeyboardMarkup(new_rows)

def replace_in_html(html_text, old_text, new_text):
    """
    Replaces text in HTML-formatted string.
    This is safer for preserving links and formatting in Telegram.
    """
    if not html_text:
        return html_text

    # We replace the text in the HTML string.
    # Note: If the old_text is part of an HTML tag (like <a href="...">),
    # this will replace it too, which is exactly what we want for replacing URLs.
    return html_text.replace(old_text, new_text)
