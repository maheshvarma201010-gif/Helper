from pyrogram import Client, filters
from bot.database.mongo import db

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await db.add_user(message.from_user.id, message.from_user.first_name)

    welcome_text = (
        "Welcome! I am an Ultimate File Sequencer & Replace Bot.\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/sequence - Start sequencing files\n"
        "/replace - Start replacing text in messages"
    )
    await message.reply_text(welcome_text)
