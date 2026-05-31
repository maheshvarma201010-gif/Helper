from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def replace_text(text, old_text, new_text):
    if not text:
        return text
    return text.replace(old_text, new_text)

def replace_in_buttons(reply_markup, old_text, new_text):
    if not reply_markup or not isinstance(reply_markup, InlineKeyboardMarkup):
        return reply_markup

    new_rows = []
    for row in reply_markup.inline_keyboard:
        new_row = []
        for button in row:
            # Create a copy of button properties
            text = replace_text(button.text, old_text, new_text)
            url = button.url
            if url:
                url = replace_text(url, old_text, new_text)

            # Reconstruct button
            if button.url:
                new_row.append(InlineKeyboardButton(text=text, url=url))
            elif button.callback_data:
                 # Usually we don't replace in callback_data unless specified,
                 # but requirement says "Replace text everywhere"
                 callback_data = button.callback_data
                 if isinstance(callback_data, str):
                     callback_data = replace_text(callback_data, old_text, new_text)
                 new_row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
            else:
                # Handle other button types if any
                new_row.append(button)
        new_rows.append(new_row)

    return InlineKeyboardMarkup(new_rows)
