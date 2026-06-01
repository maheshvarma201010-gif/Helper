from pyrogram import Client, filters
from bot.database.mongo import db

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await db.add_user(message.from_user.id, message.from_user.first_name)

    welcome_text = (
        "👋 **Welcome to the Ultimate File Sequencer & Search Bot!**\n\n"
        "I can help you sort your media collections and manage channel content.\n\n"
        "📜 **Command List:**\n"
        "• /start - Show this welcome message\n"
        "• /search `<query>` - Search indexed channel content\n"
        "• /sequence - Start collecting files for automatic sorting\n"
        "• /replace - Bulk replace text/links in channel messages\n"
        "• /replace_domain - Advanced domain replacement (Owner Only)\n"
        "• /cancel - Cancel collection/search operations\n"
        "• /cancel_replace - Stop domain replacement task\n\n"
        "🛠 **How to Sequence:**\n"
        "1. Send /sequence\n"
        "2. Forward or upload all your files\n"
        "3. Send /done when finished\n\n"
        "Powered by Userbot indexing and MongoDB."
    )
    await message.reply_text(welcome_text)
