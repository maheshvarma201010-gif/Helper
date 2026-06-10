from pyrogram import Client, filters
from bot.database.mongo import db

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await db.add_user(message.from_user.id, message.from_user.first_name)

    welcome_text = (
        "🚀 **Ultimate Forward & Watermark Bot**\n\n"
        "I can help you forward content cleanly, add custom buttons, and watermark images.\n\n"
        "📜 **Core Commands:**\n"
        "• /forward - Cleanly copy a range of messages between links\n"
        "• /ss `<session>` - Save your Pyrogram String Session\n"
        "• /auto - Configure default button templates for Auto Mode\n"
        "• /tedit - Setup and manage image watermarking\n"
        "• /replace - Bulk replace text/links in channel posts\n"
        "• /scrab `<link>` - Extract buttons from an existing post\n\n"
        "🛠 **Interactive Forwarding:**\n"
        "Just send any post or forward it to me in DM to attach buttons and repost it to your target channel without attribution.\n\n"
        "🛑 **Control:**\n"
        "• /stop - Terminate active forwarding jobs\n"
        "• /cancel - Cancel any active setup wizard"
    )
    await message.reply_text(welcome_text)
