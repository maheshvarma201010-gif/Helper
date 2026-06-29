from pyrogram import Client, filters
from pyrogram.types import Message
from bot.utils.constants import START_TEXT
from bot.database.users import add_user

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    await add_user(message.from_user.id, message.from_user.first_name)
    await message.reply(START_TEXT)
