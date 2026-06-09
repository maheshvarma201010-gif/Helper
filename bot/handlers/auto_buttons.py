import logging
from pyrogram import Client, filters
from bot.database.mongo import db

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("auto") & filters.private)
async def auto_command(client, message):
    user_id = message.from_user.id
    await db.update_user_state(user_id, "auto_awaiting_count")
    await message.reply_text("🔢 **How many buttons do you want?** (Max 10)")

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=7)
async def handle_auto_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("auto_"):
        message.continue_propagation()
        return

    text = message.text.strip()

    if state == "auto_awaiting_count":
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")
        count = int(text)
        if not (1 <= count <= 10):
            return await message.reply_text("❌ Please enter a number between 1 and 10.")

        await db.set_button_config(user_id, {"count": count, "names": [], "per_row": 2})
        await db.update_user_state(user_id, "auto_awaiting_name_1")
        await message.reply_text("🔹 Enter name for **Button 1**:")

    elif state.startswith("auto_awaiting_name_"):
        index = int(state.split("_")[-1])
        config = await db.get_button_config(user_id)

        names = config.get("names", [])
        names.append(text)
        await db.update_button_config(user_id, {"names": names})

        if index < config["count"]:
            await db.update_user_state(user_id, f"auto_awaiting_name_{index + 1}")
            await message.reply_text(f"🔹 Enter name for **Button {index + 1}**:")
        else:
            await db.update_user_state(user_id, "auto_awaiting_per_row")
            await message.reply_text("📑 **How many buttons per row?** (Example: 2)")

    elif state == "auto_awaiting_per_row":
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")
        per_row = int(text)
        if not (1 <= per_row <= 5):
            return await message.reply_text("❌ Please enter a number between 1 and 5.")

        await db.update_button_config(user_id, {"per_row": per_row})
        await db.update_user_state(user_id, None)

        config = await db.get_button_config(user_id)
        summary = (
            "✅ **Auto Buttons Configured!**\n\n"
            f"• **Count:** `{config['count']}`\n"
            f"• **Per Row:** `{config['per_row']}`\n"
            f"• **Names:** `{', '.join(config['names'])}`"
        )
        await message.reply_text(summary)
