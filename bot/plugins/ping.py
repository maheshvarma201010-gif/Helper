import time
from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("ping") & filters.private)
async def ping_handler(client: Client, message: Message):
    start = time.time()
    msg = await message.reply("Pinging...")
    end = time.time()
    await msg.edit_text(f"🏓 **Pong!**\nLatency: `{int((end - start) * 1000)}ms`")
