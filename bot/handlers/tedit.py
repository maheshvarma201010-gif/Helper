import asyncio
import os
import time
import logging
import uuid
from pyrogram import Client, filters, enums, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.database.mongo import db
from bot.utils.helpers import parse_message_link, resolve_chat
from bot.utils.watermark import apply_watermark
from bot.utils.replacer import render_message_to_html

logger = logging.getLogger(__name__)

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

# Global task queue to handle concurrency
tedit_queue = asyncio.Queue()

@Client.on_message(filters.command("tedit_status") & filters.private)
async def tedit_status_command(client, message):
    user_id = message.from_user.id
    job = await db.get_active_tedit_job(user_id)

    if not job:
        return await message.reply_text("No active TEdit jobs found.")

    text = (
        f"📊 **TEdit Job Status**\n\n"
        f"• **Job ID:** `{job['job_id']}`\n"
        f"• **Status:** `{job['status'].capitalize()}`\n"
        f"• **Type:** `{job['type']}`\n"
        f"• **Processed:** `{job.get('total_processed', 0)}` messages\n"
        f"• **Errors:** `{job.get('total_errors', 0)}`"
    )

    if job['type'] == 'range':
        progress = ((job['current_id'] - job['start_id'] + 1) / (job['end_id'] - job['start_id'] + 1)) * 100
        text += f"\n• **Progress:** `{progress:.1f}%` ({job['current_id']}/{job['end_id']})"

    buttons = []
    if job['status'] == 'running':
        buttons.append([InlineKeyboardButton("⏸ Pause", callback_data=f"tedit_job:pause:{job['job_id']}")])
    elif job['status'] == 'paused':
        buttons.append([InlineKeyboardButton("▶️ Resume", callback_data=f"tedit_job:resume:{job['job_id']}")])

    if job['status'] in ['running', 'paused', 'queued']:
        buttons.append([InlineKeyboardButton("🛑 Stop", callback_data=f"tedit_job:stop:{job['job_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

@Client.on_message(filters.command(["tedit_stop", "tedit_pause", "tedit_resume"]) & filters.private)
async def tedit_control_commands(client, message):
    user_id = message.from_user.id
    cmd = message.command[0].replace("tedit_", "")
    job = await db.get_active_tedit_job(user_id)

    if not job:
        return await message.reply_text("No active TEdit jobs found.")

    if cmd == "stop":
        await db.update_tedit_job(job['job_id'], {"status": "cancelled"})
        await message.reply_text("✅ Job stopped.")
    elif cmd == "pause":
        await db.update_tedit_job(job['job_id'], {"status": "paused"})
        await message.reply_text("✅ Job paused.")
    elif cmd == "resume":
        await db.update_tedit_job(job['job_id'], {"status": "running"})
        await tedit_queue.put(job['job_id'])
        await message.reply_text("✅ Job resumed.")

@Client.on_callback_query(filters.regex(r"^tedit_job:(.+):(.+)"))
async def handle_job_callbacks(client, callback_query):
    action = callback_query.matches[0].group(1)
    job_id = callback_query.matches[0].group(2)

    if action == "stop":
        await db.update_tedit_job(job_id, {"status": "cancelled"})
        await callback_query.answer("Job stopped.")
    elif action == "pause":
        await db.update_tedit_job(job_id, {"status": "paused"})
        await callback_query.answer("Job paused.")
    elif action == "resume":
        await db.update_tedit_job(job_id, {"status": "running"})
        await tedit_queue.put(job_id)
        await callback_query.answer("Job resumed.")

    # Refresh status message
    await tedit_status_command(client, callback_query.message)

@Client.on_message(filters.command("tedit") & filters.private)
async def tedit_command_router(client, message):
    user_id = message.from_user.id
    settings = await db.get_tedit_settings(user_id)

    # If no arguments, show setup or settings menu
    if len(message.command) == 1:
        if not settings:
            await start_setup_wizard(client, message)
        else:
            await show_settings_menu(client, message)
        return

    # If arguments, handle range or monitoring mode
    if not settings:
        return await message.reply_text("Please complete the setup first by running /tedit without arguments.")

    args = message.command[1:]

    # Check if it's a channel ID for monitoring
    if len(args) == 1 and (args[0].startswith("-100") or args[0].lstrip("-").isdigit()):
        try:
            chat_id = int(args[0])
            chat = await resolve_chat(client, chat_id)

            # Check permissions
            member = await chat.get_member(client.me.id)
            if not member.privileges or not member.privileges.can_edit_messages:
                return await message.reply_text("❌ I need 'Edit Messages' permission in that channel.")

            # Toggle monitoring
            current = await db.get_user_monitoring(user_id)
            is_monitored = any(m["channel_id"] == chat.id for m in current)

            if is_monitored:
                await db.set_tedit_monitoring(user_id, chat.id, status=False)
                return await message.reply_text(f"❌ Monitoring Disabled for `{chat.title}` ({chat.id})")
            else:
                await db.set_tedit_monitoring(user_id, chat.id, status=True)
                return await message.reply_text(
                    f"✅ Monitoring Enabled for `{chat.title}` ({chat.id})\n\n"
                    "Do you want to use Global settings or configure Custom settings for this channel?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌍 Global Settings", callback_data="tedit_menu:monitor")],
                        [InlineKeyboardButton("⚙️ Custom Settings", callback_data=f"tedit_ch_menu:{chat.id}")]
                    ])
                )
        except Exception as e:
            return await message.reply_text(f"❌ Error: {e}")

    # Message Range Mode
    if len(args) >= 2:
        # Prevent starting a new range job if one is already active
        active_job = await db.get_active_tedit_job(user_id)
        if active_job:
            return await message.reply_text("❌ You already have an active TEdit job. Please stop or wait for it to finish.")

        start_link = args[0]
        end_link = args[1]

        chat_id, start_id, _ = parse_message_link(start_link)
        chat_id_end, end_id, _ = parse_message_link(end_link)

        if not chat_id or not chat_id_end or chat_id != chat_id_end:
            return await message.reply_text("❌ Invalid links or different channels.")

        try:
            chat = await resolve_chat(client, chat_id)
            # Check permissions
            member = await chat.get_member(client.me.id)
            if not member.privileges or not member.privileges.can_edit_messages:
                return await message.reply_text("❌ I need 'Edit Messages' permission in that channel.")
        except Exception as e:
            return await message.reply_text(f"❌ Error resolving chat: {e}")

        job_id = str(uuid.uuid4())
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "chat_id": chat.id,
            "start_id": min(start_id, end_id),
            "end_id": max(start_id, end_id),
            "current_id": min(start_id, end_id),
            "status": "queued",
            "type": "range",
            "total_processed": 0,
            "total_errors": 0,
            "timestamp": time.time()
        }
        await db.add_tedit_job(job_data)
        await tedit_queue.put(job_id)
        await message.reply_text(f"✅ TEdit Job Queued! (ID: `{job_id}`)\nUse /tedit_status to track progress.")

@Client.on_message(filters.command("tedit_settings") & filters.private)
async def tedit_settings_command(client, message):
    await show_settings_menu(client, message)

@Client.on_message(filters.command("tedit_preview") & filters.private)
async def tedit_preview_command(client, message):
    user_id = message.from_user.id
    settings = await db.get_tedit_settings(user_id)

    if not settings:
        return await message.reply_text("No settings found! Please setup first using /tedit")

    # Logic same as handle_preview
    status_msg = await message.reply_text("Generating preview...")

    # Create a dummy dark image for preview
    from PIL import Image
    dummy = Image.new("RGB", (1280, 720), (30, 30, 30))
    dummy_path = f"preview_cmd_{user_id}.jpg"
    dummy.save(dummy_path)

    # Check if we need a media file
    media_path = None
    if settings.get("type") in ["logo", "sticker"]:
        media_file_id = settings.get("media_file_id")
        if media_file_id:
            try:
                media_path = await client.download_media(media_file_id)
            except Exception as e:
                logger.warning(f"Failed to download watermark media for preview: {e}")

    processed = apply_watermark(dummy_path, settings, media_path)

    if processed:
        await message.reply_photo(processed, caption="🖼 **Watermark Preview**")
        await status_msg.delete()
    else:
        await status_msg.edit_text("❌ Failed to generate preview.")

    # Cleanup
    if os.path.exists(dummy_path): os.remove(dummy_path)
    if media_path and os.path.exists(media_path): os.remove(media_path)

async def start_setup_wizard(client, message):
    text = "Welcome to the **TEdit Setup Wizard**! 🎨\n\nPlease choose your watermark type:"
    buttons = [
        [InlineKeyboardButton("Logo / Image", callback_data="tedit_set:type:logo")],
        [InlineKeyboardButton("Text Watermark", callback_data="tedit_set:type:text")],
        [InlineKeyboardButton("Sticker", callback_data="tedit_set:type:sticker")]
    ]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_settings_menu(client, message_or_query, channel_id=None):
    user_id = message_or_query.from_user.id

    if channel_id:
        # Fetch channel-specific settings
        monitoring = await db.tedit_monitoring.find_one({"user_id": user_id, "channel_id": channel_id})
        settings = (monitoring or {}).get("settings") or await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS
        title_prefix = f"📺 **Channel Settings: {channel_id}**"
        cb_prefix = f"tedit_ch:{channel_id}:"
    else:
        settings = await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS
        title_prefix = "⚙️ **TEdit Global Settings**"
        cb_prefix = "tedit_menu:"

    text = (
        f"{title_prefix}\n\n"
        f"• **Type:** `{settings.get('type')}`\n"
        f"• **Value:** `{settings.get('text') or 'Media File'}`\n"
        f"• **Position:** `{settings.get('position')}`\n"
        f"• **Opacity:** `{int(settings.get('opacity', 1.0) * 100)}%`\n"
        f"• **Size:** `{settings.get('size')}%`\n"
        f"• **Margin:** `{settings.get('margin')}px`\n"
        f"• **Rotation:** `{settings.get('rotation')}°`"
    )

    buttons = [
        [InlineKeyboardButton("Type", callback_data=f"{cb_prefix}type"),
         InlineKeyboardButton("Value", callback_data=f"{cb_prefix}value")],
        [InlineKeyboardButton("Position", callback_data=f"{cb_prefix}position"),
         InlineKeyboardButton("Opacity", callback_data=f"{cb_prefix}opacity")],
        [InlineKeyboardButton("Size", callback_data=f"{cb_prefix}size"),
         InlineKeyboardButton("Margin", callback_data=f"{cb_prefix}margin")],
        [InlineKeyboardButton("Rotation", callback_data=f"{cb_prefix}rotation")],
    ]

    if not channel_id:
        buttons.append([InlineKeyboardButton("📺 Monitor New Channel", callback_data="tedit_menu:monitor")])
        buttons.append([InlineKeyboardButton("🖼 Preview", callback_data="tedit_preview"),
                        InlineKeyboardButton("✅ Save & Close", callback_data="tedit_close")])
    else:
        buttons.append([InlineKeyboardButton("🖼 Preview", callback_data=f"tedit_preview:{channel_id}"),
                        InlineKeyboardButton("🔙 Back to Monitoring", callback_data="tedit_menu:monitor")])

    if isinstance(message_or_query, CallbackQuery):
        await message_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^tedit_menu:(.+)"))
async def handle_menu_callbacks(client, callback_query):
    action = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id

    if action == "monitor":
        # Show list of monitored channels and an option to add new
        monitors = await db.get_user_monitoring(user_id)
        text = "📺 **Monitored Channels**\n\nSelect a channel to configure custom settings or stop monitoring:"
        buttons = []
        for m in monitors:
            try:
                chat = await client.get_chat(m["channel_id"])
                title = chat.title
            except: title = f"Channel {m['channel_id']}"
            buttons.append([InlineKeyboardButton(f"⚙️ {title}", callback_data=f"tedit_ch_menu:{m['channel_id']}")])

        buttons.append([InlineKeyboardButton("➕ Add New Channel", callback_data="tedit_menu:add_channel")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="tedit_main")])
        await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "add_channel":
        await db.update_user_state(user_id, "tedit_awaiting_channel_id")
        await callback_query.message.reply_text("Please send the Channel ID (e.g., `-100...`) of the channel you want to monitor.")
        await callback_query.answer()
        return

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

@Client.on_callback_query(filters.regex(r"^tedit_ch_menu:(.+)"))
async def handle_channel_menu(client, callback_query):
    channel_id = int(callback_query.matches[0].group(1))
    await show_settings_menu(client, callback_query, channel_id=channel_id)

@Client.on_callback_query(filters.regex(r"^tedit_ch:(-?\d+):(.+)"))
async def handle_channel_settings_callbacks(client, callback_query):
    channel_id = int(callback_query.matches[0].group(1))
    action = callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id

    if action == "type":
        buttons = [
            [InlineKeyboardButton("Logo / Image", callback_data=f"tedit_ch_set:{channel_id}:type:logo")],
            [InlineKeyboardButton("Text Watermark", callback_data=f"tedit_ch_set:{channel_id}:type:text")],
            [InlineKeyboardButton("Sticker", callback_data=f"tedit_ch_set:{channel_id}:type:sticker")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"tedit_ch_menu:{channel_id}")]
        ]
        await callback_query.edit_message_text(f"Choose watermark type for channel {channel_id}:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action == "position":
        buttons = [
            [InlineKeyboardButton("Top Left", callback_data=f"tedit_ch_set:{channel_id}:pos:top_left"),
             InlineKeyboardButton("Top Center", callback_data=f"tedit_ch_set:{channel_id}:pos:top_center"),
             InlineKeyboardButton("Top Right", callback_data=f"tedit_ch_set:{channel_id}:pos:top_right")],
            [InlineKeyboardButton("Center Left", callback_data=f"tedit_ch_set:{channel_id}:pos:center_left"),
             InlineKeyboardButton("Center", callback_data=f"tedit_ch_set:{channel_id}:pos:center"),
             InlineKeyboardButton("Center Right", callback_data=f"tedit_ch_set:{channel_id}:pos:center_right")],
            [InlineKeyboardButton("Bottom Left", callback_data=f"tedit_ch_set:{channel_id}:pos:bottom_left"),
             InlineKeyboardButton("Bottom Center", callback_data=f"tedit_ch_set:{channel_id}:pos:bottom_center"),
             InlineKeyboardButton("Bottom Right", callback_data=f"tedit_ch_set:{channel_id}:pos:bottom_right")],
            [InlineKeyboardButton("Custom X/Y", callback_data=f"tedit_ch:{channel_id}:custom_pos")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"tedit_ch_menu:{channel_id}")]
        ]
        await callback_query.edit_message_text("Choose position:", reply_markup=InlineKeyboardMarkup(buttons))

    elif action in ["opacity", "size", "margin", "rotation", "value", "custom_pos"]:
        await db.update_user_state(user_id, f"tedit_ch_awaiting_{action}_{channel_id}")
        msg = {
            "opacity": f"Send opacity percentage (0-100) for channel {channel_id}:",
            "size": "Send watermark size percentage (1-100):",
            "margin": "Send margin/padding in pixels:",
            "rotation": "Send rotation angle (0-359):",
            "value": "Send the text for watermark, or send the logo image/sticker:",
            "custom_pos": "Send custom X and Y percentages (e.g., `50 50` for center):"
        }[action]
        await callback_query.message.reply_text(msg)
        await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^tedit_ch_set:(-?\d+):(.+):(.+)"))
async def handle_channel_set_callbacks(client, callback_query):
    channel_id = int(callback_query.matches[0].group(1))
    param = callback_query.matches[0].group(2)
    value = callback_query.matches[0].group(3)
    user_id = callback_query.from_user.id

    monitoring = await db.tedit_monitoring.find_one({"user_id": user_id, "channel_id": channel_id})
    settings = (monitoring or {}).get("settings") or (await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS).copy()

    if param == "type":
        settings["type"] = value
        await db.set_tedit_monitoring(user_id, channel_id, status=True, settings=settings)
        await callback_query.answer(f"Type set to {value}")
        if value == "text":
            await db.update_user_state(user_id, f"tedit_ch_awaiting_value_{channel_id}")
            await callback_query.message.reply_text("Now send the text for your watermark:")
        else:
            await db.update_user_state(user_id, f"tedit_ch_awaiting_value_{channel_id}")
            await callback_query.message.reply_text(f"Now send the {value} file:")

    elif param == "pos":
        settings["position"] = value
        await db.set_tedit_monitoring(user_id, channel_id, status=True, settings=settings)
        await callback_query.answer(f"Position set to {value}")
        await show_settings_menu(client, callback_query, channel_id=channel_id)

@Client.on_callback_query(filters.regex(r"^tedit_preview(?::(-?\d+))?$"))
async def handle_preview(client, callback_query):
    channel_id_str = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id

    if channel_id_str:
        channel_id = int(channel_id_str)
        monitoring = await db.tedit_monitoring.find_one({"user_id": user_id, "channel_id": channel_id})
        settings = (monitoring or {}).get("settings") or await db.get_tedit_settings(user_id)
    else:
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

@Client.on_message(filters.private & (filters.text | filters.photo | filters.sticker | filters.document) & ~filters.command(["tedit", "tedit_status", "tedit_stop", "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview", "start", "sequence", "sort", "replace", "replace_domain", "search", "cancel", "setchannel", "setbot", "reindex", "verify", "font", "fontchannel", "redirect", "b"]), group=2)
async def handle_settings_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or (not state.startswith("tedit_awaiting_") and not state.startswith("tedit_ch_awaiting_")):
        message.continue_propagation()
        return

    if state == "tedit_awaiting_channel_id":
        try:
            chat_id = int(message.text)
            chat = await resolve_chat(client, chat_id)

            # Check permissions
            member = await chat.get_member(client.me.id)
            if not member.privileges or not member.privileges.can_edit_messages:
                return await message.reply_text("❌ I need 'Edit Messages' permission in that channel.")

            await db.set_tedit_monitoring(user_id, chat.id, status=True)
            await db.update_user_state(user_id, None)
            await message.reply_text(f"✅ Monitoring Enabled for `{chat.title}` ({chat.id})\n\nDo you want to use Global settings or configure Custom settings for this channel?",
                                     reply_markup=InlineKeyboardMarkup([
                                         [InlineKeyboardButton("🌍 Global Settings", callback_data="tedit_menu:monitor")],
                                         [InlineKeyboardButton("⚙️ Custom Settings", callback_data=f"tedit_ch_menu:{chat.id}")]
                                     ]))
            return
        except Exception as e:
            return await message.reply_text(f"❌ Error: {e}")

    # Handle global and channel-specific settings
    is_channel = state.startswith("tedit_ch_awaiting_")
    channel_id = None
    if is_channel:
        # State format: tedit_ch_awaiting_ACTION_CHANNELID
        parts = state.replace("tedit_ch_awaiting_", "").split("_")
        action = parts[0]
        channel_id = int(parts[1]) if len(parts) > 1 else None

        monitoring = await db.tedit_monitoring.find_one({"user_id": user_id, "channel_id": channel_id})
        settings = (monitoring or {}).get("settings") or (await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS).copy()
    else:
        action = state.replace("tedit_awaiting_", "")
        settings = await db.get_tedit_settings(user_id) or DEFAULT_SETTINGS.copy()

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
            val = int(message.text.replace("%", "").strip())
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

    if is_channel and channel_id:
        await db.set_tedit_monitoring(user_id, channel_id, status=True, settings=settings)
    else:
        await db.set_tedit_settings(user_id, settings)

    await db.update_user_state(user_id, None)
    await message.reply_text("✅ Setting updated!")
    await show_settings_menu(client, message, channel_id=channel_id)

@Client.on_message(filters.channel & ~filters.service, group=1)
async def tedit_monitor_handler(client, message):
    chat_id = message.chat.id
    monitors = await db.get_tedit_monitoring(chat_id)

    if not monitors:
        return

    # We process for each user who monitors this channel
    for monitor in monitors:
        user_id = monitor["user_id"]
        # Prioritize channel-specific settings
        settings = monitor.get("settings") or await db.get_tedit_settings(user_id)
        if not settings: continue

        # Add to queue as a high-priority "single" task
        job_id = str(uuid.uuid4())
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message.id,
            "status": "queued",
            "type": "monitor",
            "settings": settings, # Store settings at time of queuing for monitor jobs
            "timestamp": time.time()
        }
        await db.add_tedit_job(job_data)
        await tedit_queue.put(job_id)

async def tedit_worker(client):
    while True:
        job_id = await tedit_queue.get()
        try:
            job = await db.get_tedit_job(job_id)
            if not job or job["status"] == "cancelled":
                continue

            await db.update_tedit_job(job_id, {"status": "running"})

            if job["type"] == "range":
                await process_range_job(client, job)
            else:
                await process_single_job(client, job)

        except Exception as e:
            logger.error(f"Worker error on job {job_id}: {e}")
        finally:
            tedit_queue.task_done()

async def process_range_job(client, job):
    job_id = job["job_id"]
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    start_id = job["current_id"]
    end_id = job["end_id"]

    settings = await db.get_tedit_settings(user_id)
    media_path = None
    if settings.get("type") in ["logo", "sticker"]:
        media_file_id = settings.get("media_file_id")
        if media_file_id:
            media_path = await client.download_media(media_file_id)

    try:
        # Avoid re-processing the last message on resume
        current_start = start_id if start_id == job.get("start_id") else start_id + 1
        for msg_id in range(current_start, end_id + 1):
            # Check if job is still active
            job = await db.get_tedit_job(job_id)
            if not job or job["status"] != "running":
                break

            try:
                msg = await client.get_messages(chat_id, msg_id)
                if not msg or msg.empty: continue

                if await process_message_watermark(client, msg, settings, media_path):
                    await db.update_tedit_job(job_id, {
                        "current_id": msg_id,
                        "total_processed": job.get("total_processed", 0) + 1
                    })

                await asyncio.sleep(0.5) # Flood protection
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logger.warning(f"Error processing {msg_id}: {e}")
                await db.update_tedit_job(job_id, {"total_errors": job.get("total_errors", 0) + 1})

        await db.update_tedit_job(job_id, {"status": "completed"})
    finally:
        if media_path and os.path.exists(media_path): os.remove(media_path)

async def process_single_job(client, job):
    job_id = job["job_id"]
    chat_id = job["chat_id"]
    user_id = job["user_id"]
    msg_id = job["message_id"]

    # Use stored settings if available (for monitor jobs), else fetch
    settings = job.get("settings") or await db.get_tedit_settings(user_id)
    media_path = None
    if settings.get("type") in ["logo", "sticker"]:
        media_file_id = settings.get("media_file_id")
        if media_file_id:
            media_path = await client.download_media(media_file_id)

    try:
        msg = await client.get_messages(chat_id, msg_id)
        if msg and not msg.empty:
            await process_message_watermark(client, msg, settings, media_path)
        await db.update_tedit_job(job_id, {"status": "completed"})
    finally:
        if media_path and os.path.exists(media_path): os.remove(media_path)

async def process_message_watermark(client, msg, settings, watermark_media_path):
    """
    Core logic to process a single message's media and update/replace it.
    """
    if not msg:
        return False

    # Handle FloodWait globally at worker level, but also here for safety
    # and handle expired file references
    photo = msg.photo
    if not photo and msg.document and msg.document.mime_type.startswith("image/"):
        photo = msg.document

    if not photo:
        return False

    try:
        # Download
        try:
            path = await client.download_media(msg)
        except errors.FileReferenceExpired:
            logger.info(f"File reference expired for {msg.id}, refreshing...")
            msg = await client.get_messages(msg.chat.id, msg.id)
            path = await client.download_media(msg)
        if not path: return False

        # Apply watermark
        processed_bytes = apply_watermark(path, settings, watermark_media_path)
        os.remove(path)

        if not processed_bytes: return False

        # Preserve metadata
        caption = render_message_to_html(msg.caption, msg.caption_entities) if msg.caption else None
        reply_markup = msg.reply_markup

        from pyrogram.types import InputMediaPhoto

        # Save processed to a temp file for upload
        temp_out = f"processed_{msg.id}_{uuid.uuid4().hex[:8]}.jpg"
        with open(temp_out, "wb") as f:
            f.write(processed_bytes.getvalue())

        # Retry logic with FloodWait handling
        for attempt in range(3):
            try:
                await client.edit_message_media(
                    chat_id=msg.chat.id,
                    message_id=msg.id,
                    media=InputMediaPhoto(temp_out, caption=caption, parse_mode=enums.ParseMode.HTML),
                    reply_markup=reply_markup
                )
                break
            except errors.FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except (errors.MessageIdInvalid, errors.MessageNotModified, errors.ChatAdminRequired, Exception) as e:
                logger.info(f"Could not edit message {msg.id}, attempting re-upload: {e}")

                # Re-upload logic
                try:
                    await client.send_photo(
                        chat_id=msg.chat.id,
                        photo=temp_out,
                        caption=caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                    # Optionally delete old message if possible
                    try:
                        await client.delete_messages(msg.chat.id, msg.id)
                    except: pass
                    break
                except errors.FloodWait as fe:
                    await asyncio.sleep(fe.value + 1)
                except Exception as re_e:
                    logger.error(f"Failed to re-upload {msg.id} on attempt {attempt}: {re_e}")
                    if attempt == 2:
                        if os.path.exists(temp_out): os.remove(temp_out)
                        return False
                    await asyncio.sleep(1)

        if os.path.exists(temp_out): os.remove(temp_out)
        return True
    except Exception as e:
        logger.error(f"Error in process_message_watermark: {e}")
        return False

# Initialize worker and resume pending jobs
async def init_worker(client, concurrency=3):
    logger.info(f"Initializing TEdit worker (concurrency={concurrency}) and resuming pending jobs...")
    active_jobs = await db.get_all_active_tedit_jobs()
    for job in active_jobs:
        if job["status"] in ["running", "queued"]:
            await tedit_queue.put(job["job_id"])
            logger.info(f"Resumed job {job['job_id']}")

    for _ in range(concurrency):
        asyncio.create_task(tedit_worker(client))
