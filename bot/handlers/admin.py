from pyrogram import Client, filters
from bot.config import Config
from bot.database.mongo import db
from bot.utils.indexer import index_channel

@Client.on_message(filters.command("setchannel") & filters.user(Config.ADMINS))
async def set_channel_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /setchannel -100xxxxxxxxxx")

    channel_id = message.command[1]
    try:
        channel_id = int(channel_id)
        await db.set_source_channel(channel_id)
        await message.reply_text("Source channel updated successfully.")
    except ValueError:
        await message.reply_text("Invalid Channel ID.")

@Client.on_message(filters.command("setbot") & filters.user(Config.ADMINS))
async def set_bot_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /setbot @DeepLinkBot")

    bot_username = message.command[1].replace("@", "")
    await db.set_batch_bot(bot_username)
    await message.reply_text("Batch bot updated successfully.")

@Client.on_message(filters.command("reindex") & filters.user(Config.ADMINS))
async def reindex_command(client, message):
    source_id = await db.get_source_channel()
    if not source_id:
        return await message.reply_text("Source channel not set. Use /setchannel first.")

    progress = await message.reply_text("Starting indexing...")
    # client.userbot is accessible because we attached it in Bot.__init__
    count = await index_channel(client.userbot, source_id, progress)

    if count >= 0:
        await progress.edit_text(f"Indexing complete! Added {count} messages.")
    else:
        await progress.edit_text("Indexing failed. Check logs.")
