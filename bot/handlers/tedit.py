import asyncio
import os
import time
from pyrogram import Client, filters, enums, errors
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, InputMediaDocument
from bot.database.mongo import db
from bot.utils.watermarker import apply_watermark
from bot.utils.helpers import resolve_chat, parse_message_link
from bot.config import Config

# Setup states
STATE_IDLE = None
STATE_WAIT_CONTENT = "tedit:wait_content"
STATE_WAIT_CUSTOM_XY = "tedit:wait_xy"

@Client.on_message(filters.command("tedit_status") & filters.private)
async def tedit_status_cmd(client, message):
    task = await db.get_tedit_task(message.from_user.id)
    if not task:
        return await message.reply_text("❌ No active TEdit task.")

    await message.reply_text(
        f"📊 **TEdit Task Status**\n\n"
        f"Type: `{task['type'].capitalize()}`\n"
        f"Status: `{task['status'].capitalize()}`\n"
        f"Processed: `{task['processed']}` messages\n"
        f"Target: `{task['chat_id']}`"
    )

@Client.on_message(filters.command("tedit_stop") & filters.private)
async def tedit_stop_cmd(client, message):
    await db.delete_tedit_task(message.from_user.id)
    await message.reply_text("🛑 TEdit task stopped and cleared.")

@Client.on_message(filters.command("tedit_pause") & filters.private)
async def tedit_pause_cmd(client, message):
    await db.update_tedit_task(message.from_user.id, {"status": "paused"})
    await message.reply_text("⏸ TEdit task paused.")

@Client.on_message(filters.command("tedit_resume") & filters.private)
async def tedit_resume_cmd(client, message):
    task = await db.get_tedit_task(message.from_user.id)
    if task:
        await db.update_tedit_task(message.from_user.id, {"status": "running"})
        await message.reply_text("▶️ TEdit task resumed.")
        if task["type"] == "range":
            status_msg = await message.reply_text("🚀 Resuming range task...")
            asyncio.create_task(process_range_task(client, status_msg, message.from_user.id))

@Client.on_message(filters.command("tedit_settings") & filters.private)
async def tedit_settings_cmd(client, message):
    await start_wizard(message)

@Client.on_message(filters.command("tedit_preview") & filters.private)
async def tedit_preview_cmd(client, message):
    user_id = message.from_user.id
    settings = await db.get_tedit_settings(user_id)
    if not settings:
        return await message.reply_text("❌ Configure your watermark first with /tedit.")

    status = await message.reply_text("🖼 Generating preview...")
    # Use a generic background for preview
    preview_bg = "bot/web/static/images/preview_bg.png" # Assuming it exists or use default
    if not os.path.exists(preview_bg):
        # Create a simple dummy BG if missing
        from PIL import Image
        img = Image.new('RGB', (1280, 720), color = (73, 109, 137))
        os.makedirs("bot/web/static/images", exist_ok=True)
        img.save(preview_bg)

    out = f"preview_{user_id}.png"
    await asyncio.to_thread(apply_watermark, preview_bg, out, settings)
    await message.reply_photo(out, caption="🖼 **TEdit Watermark Preview**")
    os.remove(out)
    await status.delete()

@Client.on_message(filters.command("tedit") & filters.private)
async def tedit_cmd(client, message: Message):
    user_id = message.from_user.id
    settings = await db.get_tedit_settings(user_id)

    if not settings:
        return await start_wizard(message)

    if len(message.command) < 2:
        return await message.reply_text(
            "ℹ️ **TEdit Usage:**\n\n"
            "**Range Mode:**\n"
            "`/tedit <start_link> <end_link>`\n\n"
            "**Monitoring Mode:**\n"
            "`/tedit <channel_id>`"
        )

    args = message.command[1:]
    if len(args) == 1:
        # Monitoring Mode
        channel_query = args[0]
        try:
            chat = await resolve_chat(client, channel_query)
            await db.add_tedit_task(user_id, {
                "type": "monitoring",
                "chat_id": chat.id,
                "status": "running",
                "processed": 0
            })
            await message.reply_text(f"✅ **Monitoring enabled for `{chat.title}`**\nNew posts with images will be watermarked automatically.")
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
    else:
        # Range Mode
        start_link = args[0]
        end_link = args[1]

        chat_id, first_id, last_id = parse_message_link(start_link)
        _, _, final_id = parse_message_link(end_link)

        if not chat_id or not first_id or not final_id:
            return await message.reply_text("❌ Invalid links provided.")

        await db.add_tedit_task(user_id, {
            "type": "range",
            "chat_id": chat_id,
            "first_id": first_id,
            "last_id": final_id,
            "current_id": first_id,
            "status": "running",
            "processed": 0
        })

        status_msg = await message.reply_text("🚀 **Starting message range task...**")
        asyncio.create_task(process_range_task(client, status_msg, user_id))

async def start_wizard(message):
    buttons = [
        [InlineKeyboardButton("Logo/Image", callback_data="tedit:type:logo")],
        [InlineKeyboardButton("Text Watermark", callback_data="tedit:type:text")],
        [InlineKeyboardButton("Sticker", callback_data="tedit:type:sticker")]
    ]
    await message.reply_text(
        "👋 **Welcome to the TEdit Setup Wizard!**\n\n"
        "To get started, choose the type of watermark you want to apply:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^tedit:"))
async def tedit_callback(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data.split(":")

    if data[1] == "type":
        w_type = data[2]
        await db.set_tedit_settings(user_id, {"type": w_type})
        await db.update_user_state(user_id, STATE_WAIT_CONTENT)
        prompt = "Please send your Logo image." if w_type == "logo" else \
                 "Please send the text for your watermark." if w_type == "text" else \
                 "Please send your sticker."
        await callback.message.edit_text(f"✅ Type set to `{w_type}`.\n\n{prompt}")

    elif data[1] == "pos":
        pos = data[2]
        await db.set_tedit_settings(user_id, {"position": pos})
        if pos == "custom":
            await db.update_user_state(user_id, STATE_WAIT_CUSTOM_XY)
            await callback.message.edit_text("Send custom X and Y coordinates (e.g., `100 200`):")
        else:
            await show_style_settings(callback.message, user_id)

    elif data[1] == "style":
        # Handle opacity, size, margin, rotation buttons
        attr = data[2]
        val = float(data[3])
        settings = await db.get_tedit_settings(user_id)
        current = settings.get(attr, 0)
        new_val = current + val
        if attr == "opacity": new_val = round(max(0.1, min(1.0, new_val)), 1)
        elif attr == "size": new_val = max(1, min(100, new_val))

        await db.set_tedit_settings(user_id, {attr: new_val})
        await show_style_settings(callback.message, user_id)

    elif data[1] == "finish":
        await callback.message.edit_text("✅ **Watermark setup complete!**\n\nYou can now use `/tedit <links>` or `/tedit <channel_id>`.")

@Client.on_message(filters.private & ~filters.command(["tedit", "tedit_status", "tedit_stop", "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview", "start", "sequence", "sort", "search"]))
async def tedit_input_handler(client, message: Message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state == STATE_WAIT_CONTENT:
        settings = await db.get_tedit_settings(user_id)
        w_type = settings["type"]

        content = None
        if w_type == "logo" and message.photo:
            content = await message.download(f"downloads/wm_{user_id}.png")
        elif w_type == "sticker" and message.sticker:
            content = await message.download(f"downloads/wm_{user_id}.webp")
        elif w_type == "text" and message.text:
            content = message.text

        if not content:
            return await message.reply_text(f"❌ Invalid input for `{w_type}`. Please try again.")

        await db.set_tedit_settings(user_id, {"content": content})
        await db.update_user_state(user_id, STATE_IDLE)

        # Show position menu
        await show_position_menu(message)

    elif state == STATE_WAIT_CUSTOM_XY:
        try:
            x, y = map(int, message.text.split())
            await db.set_tedit_settings(user_id, {"custom_x": x, "custom_y": y})
            await db.update_user_state(user_id, STATE_IDLE)
            await show_style_settings(message, user_id)
        except:
            await message.reply_text("❌ Invalid format. Send two numbers separated by space.")

async def show_position_menu(message):
    pos_list = [
        ("Top Left", "top_left"), ("Top Center", "top_center"), ("Top Right", "top_right"),
        ("Center Left", "center_left"), ("Center", "center"), ("Center Right", "center_right"),
        ("Bottom Left", "bottom_left"), ("Bottom Center", "bottom_center"), ("Bottom Right", "bottom_right"),
        ("Custom", "custom")
    ]
    buttons = []
    for i in range(0, len(pos_list), 3):
        row = [InlineKeyboardButton(text, callback_data=f"tedit:pos:{data}") for text, data in pos_list[i:i+3]]
        buttons.append(row)

    await message.reply_text("Select watermark position:", reply_markup=InlineKeyboardMarkup(buttons))

async def show_style_settings(message, user_id):
    s = await db.get_tedit_settings(user_id)
    text = (
        "🛠 **Watermark Styling**\n\n"
        f"Opacity: `{s.get('opacity', 1.0)}`\n"
        f"Size: `{s.get('size', 10)}%`\n"
        f"Margin: `{s.get('margin', 20)}px`\n"
        f"Rotation: `{s.get('rotation', 0)}°`"
    )
    buttons = [
        [
            InlineKeyboardButton("Opacity -", callback_data="tedit:style:opacity:-0.1"),
            InlineKeyboardButton("Opacity +", callback_data="tedit:style:opacity:0.1")
        ],
        [
            InlineKeyboardButton("Size -", callback_data="tedit:style:size:-5"),
            InlineKeyboardButton("Size +", callback_data="tedit:style:size:5")
        ],
        [
            InlineKeyboardButton("Margin -", callback_data="tedit:style:margin:-10"),
            InlineKeyboardButton("Margin +", callback_data="tedit:style:margin:10")
        ],
        [
            InlineKeyboardButton("Rotate -", callback_data="tedit:style:rotation:-45"),
            InlineKeyboardButton("Rotate +", callback_data="tedit:style:rotation:45")
        ],
        [InlineKeyboardButton("✅ Finish Setup", callback_data="tedit:finish")]
    ]
    if isinstance(message, Message):
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def process_range_task(client, status_msg, user_id):
    task = await db.get_tedit_task(user_id)
    settings = await db.get_tedit_settings(user_id)
    chat_id = task["chat_id"]

    for msg_id in range(task["current_id"], task["last_id"] + 1):
        # Refresh task state
        task = await db.get_tedit_task(user_id)
        if not task or task["status"] == "stopped": break
        if task["status"] == "paused":
            while task["status"] == "paused":
                await asyncio.sleep(5)
                task = await db.get_tedit_task(user_id)

        try:
            msg = await client.get_messages(chat_id, msg_id)
            if not msg or msg.empty: continue

            if msg.photo or (msg.document and msg.document.mime_type.startswith("image/")):
                temp_in = await msg.download()
                temp_out = f"processed_{msg_id}.png"
                await asyncio.to_thread(apply_watermark, temp_in, temp_out, settings)

                # Edit or re-upload
                try:
                    await client.edit_message_media(
                        chat_id, msg_id,
                        media=InputMediaPhoto(temp_out, caption=msg.caption, caption_entities=msg.caption_entities)
                    )
                except:
                    # If edit fails, re-upload
                    await client.send_photo(chat_id, temp_out, caption=msg.caption, caption_entities=msg.caption_entities, reply_markup=msg.reply_markup)

                os.remove(temp_in)
                os.remove(temp_out)

            task["processed"] += 1
            await db.update_tedit_task(user_id, {"current_id": msg_id + 1, "processed": task["processed"]})

            if status_msg and task["processed"] % 5 == 0:
                try:
                    await status_msg.edit_text(f"⏳ **Processing Range...**\n`{task['processed']}` messages completed.")
                except: pass

        except errors.FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.error(f"Error processing {msg_id}: {e}")

    if status_msg:
        try:
            await status_msg.edit_text(f"✅ **Task Completed!**\nProcessed `{task['processed']}` messages.")
        except: pass
    await db.delete_tedit_task(user_id)

@Client.on_message(filters.channel)
async def channel_monitor_handler(client, message: Message):
    # Find all tasks monitoring this channel
    active_monitors = await db.tedit_tasks.find({"type": "monitoring", "chat_id": message.chat.id, "status": "running"}).to_list(length=None)

    if not active_monitors:
        return

    # Process watermark for each user monitoring this channel
    for task in active_monitors:
        user_id = task["user_id"]
        settings = await db.get_tedit_settings(user_id)

        if message.photo or (message.document and message.document.mime_type.startswith("image/")):
            try:
                temp_in = await message.download()
                temp_out = f"mon_{message.id}_{user_id}.png"
                await asyncio.to_thread(apply_watermark, temp_in, temp_out, settings)

                # Update the channel post
                try:
                    await client.edit_message_media(
                        message.chat.id, message.id,
                        media=InputMediaPhoto(temp_out, caption=message.caption, caption_entities=message.caption_entities)
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit monitored post: {e}")

                os.remove(temp_in)
                os.remove(temp_out)

                # Update stats
                await db.update_tedit_task(user_id, {"processed": task.get("processed", 0) + 1})
            except Exception as e:
                logger.error(f"Monitor error for user {user_id}: {e}")
