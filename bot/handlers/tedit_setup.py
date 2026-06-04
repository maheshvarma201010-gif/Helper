import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.database.mongo import db
from bot.utils.watermark import apply_watermark

# Default settings
DEFAULT_SETTINGS = {
    "type": "text",
    "text": "@your_username",
    "position": "bottom_right",
    "opacity": 0.8,
    "size": 15,
    "margin": 20,
    "rotation": 0,
    "custom_x": 0,
    "custom_y": 0
}

@Client.on_message(filters.command("tedit") & filters.private)
async def tedit_command(client, message):
    user_id = message.from_user.id
    settings = await db.get_tedit_settings(user_id)

    # Check for range/channel ID arguments
    if len(message.command) > 1:
        # This will be handled in tedit.py, but we check if setup is done first
        if not settings:
            await message.reply_text("Please complete the setup first by running /tedit without arguments.")
            return
        # If arguments provided, don't trigger setup wizard here
        # (Assuming tedit.py is also registered and will pick this up)
        return

    if not settings:
        await start_setup_wizard(client, message)
    else:
        await show_settings_menu(client, message)

@Client.on_message(filters.command("tedit_settings") & filters.private)
async def tedit_settings_command(client, message):
    await show_settings_menu(client, message)

async def start_setup_wizard(client, message):
    text = "Welcome to the **TEdit Setup Wizard**! 🎨\n\nPlease choose your watermark type:"
    buttons = [
        [InlineKeyboardButton("Logo / Image", callback_data="tedit_set:type:logo")],
        [InlineKeyboardButton("Text Watermark", callback_data="tedit_set:type:text")],
        [InlineKeyboardButton("Sticker", callback_data="tedit_set:type:sticker")]
    ]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_settings_menu(client, message_or_query):
    user_id = message_or_query.from_user.id
    settings = await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS

    text = (
        "⚙️ **TEdit Watermark Settings**\n\n"
        f"• **Type:** `{settings.get('type')}`\n"
        f"• **Value:** `{settings.get('text') or 'Media File'}`\n"
        f"• **Position:** `{settings.get('position')}`\n"
        f"• **Opacity:** `{int(settings.get('opacity', 1.0) * 100)}%`\n"
        f"• **Size:** `{settings.get('size')}%`\n"
        f"• **Margin:** `{settings.get('margin')}px`\n"
        f"• **Rotation:** `{settings.get('rotation')}°`"
    )

    buttons = [
        [InlineKeyboardButton("Type", callback_data="tedit_menu:type"),
         InlineKeyboardButton("Value", callback_data="tedit_menu:value")],
        [InlineKeyboardButton("Position", callback_data="tedit_menu:position"),
         InlineKeyboardButton("Opacity", callback_data="tedit_menu:opacity")],
        [InlineKeyboardButton("Size", callback_data="tedit_menu:size"),
         InlineKeyboardButton("Margin", callback_data="tedit_menu:margin")],
        [InlineKeyboardButton("Rotation", callback_data="tedit_menu:rotation")],
        [InlineKeyboardButton("🖼 Preview", callback_data="tedit_preview"),
         InlineKeyboardButton("✅ Save & Close", callback_data="tedit_close")]
    ]

    if isinstance(message_or_query, CallbackQuery):
        await message_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^tedit_menu:(.+)"))
async def handle_menu_callbacks(client, callback_query):
    action = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id

    if action == "type":
        buttons = [
            [InlineKeyboardButton("Logo / Image", callback_data="tedit_set:type:logo")],
            [InlineKeyboardButton("Text Watermark", callback_data="tedit_set:type:text")],
            [InlineKeyboardButton("Sticker", callback_data="tedit_set:type:sticker")],
            [InlineKeyboardButton("🔙 Back", callback_data="tedit_main")]
        ]
        await callback_query.edit_message_text("Choose watermark type:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "position":
        buttons = [
            [InlineKeyboardButton("Top Left", callback_data="tedit_set:pos:top_left"),
             InlineKeyboardButton("Top Center", callback_data="tedit_set:pos:top_center"),
             InlineKeyboardButton("Top Right", callback_data="tedit_set:pos:top_right")],
            [InlineKeyboardButton("Center Left", callback_data="tedit_set:pos:center_left"),
             InlineKeyboardButton("Center", callback_data="tedit_set:pos:center"),
             InlineKeyboardButton("Center Right", callback_data="tedit_set:pos:center_right")],
            [InlineKeyboardButton("Bottom Left", callback_data="tedit_set:pos:bottom_left"),
             InlineKeyboardButton("Bottom Center", callback_data="tedit_set:pos:bottom_center"),
             InlineKeyboardButton("Bottom Right", callback_data="tedit_set:pos:bottom_right")],
            [InlineKeyboardButton("Custom X/Y", callback_data="tedit_menu:custom_pos")],
            [InlineKeyboardButton("🔙 Back", callback_data="tedit_main")]
        ]
        await callback_query.edit_message_text("Choose position:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action in ["opacity", "size", "margin", "rotation", "value", "custom_pos"]:
        await db.update_user_state(user_id, f"tedit_awaiting_{action}")
        msg = {
            "opacity": "Send opacity percentage (0-100):",
            "size": "Send watermark size percentage (1-100):",
            "margin": "Send margin/padding in pixels:",
            "rotation": "Send rotation angle (0-359):",
            "value": "Send the text for watermark, or send the logo image/sticker:",
            "custom_pos": "Send custom X and Y percentages (e.g., `50 50` for center):"
        }[action]
        await callback_query.message.reply_text(msg)
        await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^tedit_set:(.+):(.+)"))
async def handle_set_callbacks(client, callback_query):
    param = callback_query.matches[0].group(1)
    value = callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id

    settings = await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS.copy()

    if param == "type":
        settings["type"] = value
        await db.set_tedit_settings(user_id, settings)
        await callback_query.answer(f"Type set to {value}")
        if value == "text":
            await db.update_user_state(user_id, "tedit_awaiting_value")
            await callback_query.message.reply_text("Now send the text for your watermark:")
        else:
            await db.update_user_state(user_id, "tedit_awaiting_value")
            await callback_query.message.reply_text(f"Now send the {value} file:")

    elif param == "pos":
        settings["position"] = value
        await db.set_tedit_settings(user_id, settings)
        await callback_query.answer(f"Position set to {value}")
        await show_settings_menu(client, callback_query)

@Client.on_callback_query(filters.regex(r"^tedit_main$"))
async def handle_main_menu(client, callback_query):
    await show_settings_menu(client, callback_query)

@Client.on_callback_query(filters.regex(r"^tedit_close$"))
async def handle_close(client, callback_query):
    await callback_query.message.delete()

@Client.on_callback_query(filters.regex(r"^tedit_preview$"))
async def handle_preview(client, callback_query):
    user_id = callback_query.from_user.id
    settings = await db.get_tedit_settings(user_id)

    if not settings:
        return await callback_query.answer("No settings found!")

    await callback_query.answer("Generating preview...")

    # Create a dummy dark image for preview
    from PIL import Image
    dummy = Image.new("RGB", (1280, 720), (30, 30, 30))
    dummy_path = f"preview_{user_id}.jpg"
    dummy.save(dummy_path)

    # Check if we need a media file
    media_path = None
    if settings.get("type") in ["logo", "sticker"]:
        media_file_id = settings.get("media_file_id")
        if media_file_id:
            media_path = await client.download_media(media_file_id)

    processed = apply_watermark(dummy_path, settings, media_path)

    if processed:
        await callback_query.message.reply_photo(processed, caption="🖼 **Watermark Preview**")
    else:
        await callback_query.message.reply_text("❌ Failed to generate preview.")

    # Cleanup
    if os.path.exists(dummy_path): os.remove(dummy_path)
    if media_path and os.path.exists(media_path): os.remove(media_path)

@Client.on_message(filters.private & filters.create(lambda _, __, m: m.text or m.photo or m.sticker or m.document))
async def handle_settings_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("tedit_awaiting_"):
        return

    settings = await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS.copy()
    action = state.replace("tedit_awaiting_", "")

    if action == "value":
        if settings["type"] == "text":
            if not message.text:
                return await message.reply_text("Please send text.")
            settings["text"] = message.text
        else:
            media = message.photo or message.sticker or message.document
            if not media:
                return await message.reply_text(f"Please send a {settings['type']}.")
            settings["media_file_id"] = media.file_id
            settings["text"] = None # Clear text if media is set

    elif action == "opacity":
        try:
            val = float(message.text) / 100.0
            if 0 <= val <= 1.0:
                settings["opacity"] = val
            else: raise ValueError()
        except: return await message.reply_text("Invalid value. Send a number between 0 and 100.")

    elif action == "size":
        try:
            val = int(message.text)
            if 1 <= val <= 100:
                settings["size"] = val
            else: raise ValueError()
        except: return await message.reply_text("Invalid value. Send a number between 1 and 100.")

    elif action == "margin":
        try:
            settings["margin"] = int(message.text)
        except: return await message.reply_text("Invalid value. Send a number.")

    elif action == "rotation":
        try:
            settings["rotation"] = int(message.text) % 360
        except: return await message.reply_text("Invalid value. Send a number.")

    elif action == "custom_pos":
        try:
            parts = message.text.split()
            settings["custom_x"] = int(parts[0])
            settings["custom_y"] = int(parts[1])
            settings["position"] = "custom"
        except: return await message.reply_text("Invalid format. Send two numbers, e.g., `50 50`.")

    await db.set_tedit_settings(user_id, settings)
    await db.update_user_state(user_id, None)
    await message.reply_text("✅ Setting updated!")
    await show_settings_menu(client, message)
