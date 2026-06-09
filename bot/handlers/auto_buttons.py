import logging
from pyrogram import Client, filters
from bot.database.mongo import db

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("auto") & filters.private)
async def auto_command(client, message):
    user_id = message.from_user.id
    await db.update_user_state(user_id, "awaiting_button_count")
    await message.reply_text("How many buttons do you want to add? (Enter a number)")

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=7)
async def handle_auto_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or (not state.startswith("awaiting_button_") and state != "awaiting_forward_tag"):
        message.continue_propagation()
        return

    text = message.text.strip()

    if state == "awaiting_button_count":
        if not text.isdigit():
            return await message.reply_text("❌ Please enter a valid number.")

        count = int(text)
        if count <= 0 or count > 10:
            return await message.reply_text("❌ Please enter a number between 1 and 10.")

        await db.button_configs.update_one(
            {"user_id": user_id},
            {"$set": {"count": count, "names": [], "urls": []}},
            upsert=True
        )
        await db.update_user_state(user_id, "awaiting_button_name_1")
        await message.reply_text(f"Enter name for **Button 1**:")

    elif state.startswith("awaiting_button_name_"):
        index = int(state.split("_")[-1])
        config = await db.get_button_config(user_id)

        names = config.get("names", [])
        names.append(text)

        await db.button_configs.update_one({"user_id": user_id}, {"$set": {"names": names}})
        await db.update_user_state(user_id, f"awaiting_button_url_{index}")
        await message.reply_text(f"Enter URL for **Button {index}**:")

    elif state.startswith("awaiting_button_url_"):
        index = int(state.split("_")[-1])
        config = await db.get_button_config(user_id)

        if not text.startswith(("http://", "https://")):
             return await message.reply_text("❌ Invalid URL. Must start with http:// or https://")

        urls = config.get("urls", [])
        urls.append(text)
        await db.button_configs.update_one({"user_id": user_id}, {"$set": {"urls": urls}})

        if index < config["count"]:
            await db.update_user_state(user_id, f"awaiting_button_name_{index + 1}")
            await message.reply_text(f"Enter name for **Button {index + 1}**:")
        else:
            await db.update_user_state(user_id, "awaiting_forward_tag")
            await message.reply_text("Last step! Enter the **Forward Tag**.\n(Buttons will only be attached if this text is found in the caption/text)")

    elif state == "awaiting_forward_tag":
        await db.button_configs.update_one({"user_id": user_id}, {"$set": {"tag": text}})
        await db.update_user_state(user_id, None)

        config = await db.get_button_config(user_id)
        summary = (
            "✅ **Auto Buttons Configured!**\n\n"
            f"• **Buttons:** {config['count']}\n"
            f"• **Tag:** `{config['tag']}`\n\n"
            "**Button Preview:**\n"
        )
        for name, url in zip(config['names'], config['urls']):
            summary += f"- [{name}]({url})\n"

        await message.reply_text(summary, disable_web_page_preview=True)
