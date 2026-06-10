import logging
from pyrogram import Client, filters
from bot.database.mongo import db

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("auto") & filters.private)
async def auto_command(client, message):
    user_id = message.from_user.id
    await db.reset_user(user_id)
    await db.update_user_state(user_id, "awaiting_button_count")
    await message.reply_text("🔢 **Auto Buttons Setup**\n\nHow many buttons do you want to add? (Enter a number)")

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=7)
async def handle_auto_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or (not state.startswith("awaiting_button_") and state != "awaiting_buttons_per_row"):
        message.continue_propagation()
        return

    text = message.text.strip()

    if state == "awaiting_button_count":
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")

        count = int(text)
        if count <= 0 or count > 20:
            return await message.reply_text("❌ Please enter a number between 1 and 20.")

        await db.set_button_config(user_id, {"count": count, "names": [], "rows": 1})
        await db.update_user_state(user_id, "awaiting_button_name_1")
        await message.reply_text(f"Enter name for **Button 1**:")

    elif state.startswith("awaiting_button_name_"):
        index = int(state.split("_")[-1])
        config = await db.get_button_config(user_id)
        if not config:
            return await message.reply_text("❌ Session expired. Please start over with /auto")

        names = config.get("names", [])
        names.append(text)

        await db.set_button_config(user_id, {"names": names})

        if index < config["count"]:
            await db.update_user_state(user_id, f"awaiting_button_name_{index + 1}")
            await message.reply_text(f"Enter name for **Button {index + 1}**:")
        else:
            await db.update_user_state(user_id, "awaiting_buttons_per_row")
            await message.reply_text("✅ All names saved.\n\nHow many **buttons per row**? (Enter a number)")

    elif state == "awaiting_buttons_per_row":
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")

        rows = int(text)
        if rows <= 0 or rows > 5:
            return await message.reply_text("❌ Please enter a number between 1 and 5.")

        await db.set_button_config(user_id, {"rows": rows})
        await db.update_user_state(user_id, None)

        config = await db.get_button_config(user_id)
        summary = (
            "✅ **Auto Buttons Configured!**\n\n"
            f"• **Total Buttons:** {config['count']}\n"
            f"• **Buttons Per Row:** {config['rows']}\n\n"
            "**Button Names:**\n"
        )
        for i, name in enumerate(config['names'], 1):
            summary += f"{i}. {name}\n"

        summary += "\n*Note: Links will be requested during forwarding in Auto Mode.*"

        await message.reply_text(summary)
