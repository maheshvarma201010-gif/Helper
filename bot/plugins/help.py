from pyrogram import Client, filters
from pyrogram.types import Message
from bot.utils.constants import HELP_TEXT

@Client.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    await message.reply(HELP_TEXT)
