import logging
from pyrogram import Client, filters
from bot.database.mongo import db
from bot.handlers.forward import get_user_client
from bot.utils.helpers import parse_message_link

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("scrab") & filters.private)
async def scrab_command(client, message):
    user_id = message.from_user.id
    link = None

    if len(message.command) > 1:
        link = message.command[1]
    elif message.reply_to_message and message.reply_to_message.text:
        link = message.reply_to_message.text.strip()

    if not link:
        return await message.reply_text("❌ Please provide a message link or reply to one.\nExample: `/scrab https://t.me/c/123/456`")

    chat_id, msg_id, _ = parse_message_link(link)
    if not chat_id or not msg_id:
        return await message.reply_text("❌ Invalid message link.")

    user_client = await get_user_client(user_id)
    if not user_client:
        return await message.reply_text("❌ Please save your string session first using /ss")

    try:
        msg = await user_client.get_messages(chat_id, msg_id)
        if not msg or msg.empty:
            return await message.reply_text("❌ Could not find message.")

        if not msg.reply_markup or not msg.reply_markup.inline_keyboard:
            return await message.reply_text("❌ This message has no attached buttons.")

        button_names = []
        for row in msg.reply_markup.inline_keyboard:
            for btn in row:
                button_names.append(btn.text)

        response = "✅ **Extracted Button Names:**\n\n"
        for i, name in enumerate(button_names, 1):
            response += f"{i}. `{name}`\n"

        await message.reply_text(response)

    except Exception as e:
        logger.error(f"Scrab error: {e}")
        await message.reply_text(f"❌ Error: `{e}`")
