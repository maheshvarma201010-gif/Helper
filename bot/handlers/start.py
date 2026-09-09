from pyrogram import Client, filters
from bot.database.mongo import db

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await db.add_user(message.from_user.id, message.from_user.first_name)

    welcome_text = (
        "🚀 **File-to-Link & Multi-Audio Player Bot**\n\n"
        "Send or forward any video or document (MKV / MP4) to extract all audio tracks and generate instant Watch & Download URLs!\n\n"
        "📜 **Primary Commands:**\n"
        "• /start - Start the bot & view instructions\n"
        "• /link - Generate Watch & Download links for a message link or replied file\n\n"
        "🎬 **Features:**\n"
        "• 📥 **Direct Download Links:** Browser fast download support for Chrome/Edge/Firefox.\n"
        "• 🍿 **Web Watch Player:** Watch online with dynamic audio track switcher powered by FFmpeg.wasm.\n"
        "• 🎵 **Multi-Audio Extraction:** Automatically extracts all embedded audio streams (English, Hindi, Japanese, etc.).\n\n"
        "🛠 **Other Features:**\n"
        "• /forward - Cleanly copy a range of messages between links\n"
        "• /ss `<session>` - Save your Pyrogram String Session\n"
        "• /auto - Configure default button templates\n"
        "• /tedit - Setup image watermarking\n"
        "• /stop - Terminate active forwarding jobs"
    )
    await message.reply_text(welcome_text)
