from typing import List
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.constants import MessageTypes

def get_filter_keyboard(selected_filters: List[str]) -> InlineKeyboardMarkup:
    buttons = []

    # 2 buttons per row
    for i in range(0, len(MessageTypes.ALL_TYPES), 2):
        row = []
        for j in range(2):
            if i + j < len(MessageTypes.ALL_TYPES):
                filter_type = MessageTypes.ALL_TYPES[i + j]
                prefix = "✅ " if filter_type in selected_filters else "❌ "
                row.append(InlineKeyboardButton(
                    f"{prefix}{filter_type}",
                    callback_data=f"toggle_{filter_type}"
                ))
        buttons.append(row)

    # Bulk actions
    buttons.append([
        InlineKeyboardButton("✅ Select All", callback_data="select_all"),
        InlineKeyboardButton("❌ Clear All", callback_data="clear_all")
    ])

    # Done button
    buttons.append([
        InlineKeyboardButton("🚀 Start Forwarding", callback_data="start_forward")
    ])

    return InlineKeyboardMarkup(buttons)
