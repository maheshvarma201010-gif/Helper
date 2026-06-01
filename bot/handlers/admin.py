from pyrogram import Client, filters
from bot.config import Config
from bot.database.mongo import db
from bot.utils.indexer import index_channel
from bot.utils.helpers import resolve_chat

@Client.on_message(filters.command("setchannel") & filters.user(Config.ADMINS))
async def set_channel_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /setchannel -100xxxxxxxxxx")

    channel_id = message.command[1]
    try:
        # Try to resolve first to ensure access
        worker = client
        chat = await resolve_chat(worker, channel_id)
        await db.set_source_channel(chat.id)
        await message.reply_text(f"✅ Source channel updated to `{chat.title}` ({chat.id}) and cached.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

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
        return await message.reply_text("Source channel not set.")

    progress = await message.reply_text("Starting indexing...")
    count = await index_channel(client, source_id, progress)

    if count >= 0:
        await progress.edit_text(f"Indexing complete! Added {count} messages.")
    else:
        await progress.edit_text("Indexing failed.")

@Client.on_message(filters.command("verify") & filters.user(Config.ADMINS))
async def verify_command(client, message):
    source_id = await db.get_source_channel()
    channels = list(Config.REPLACE_TEXT_CHANNELS)
    if source_id:
        channels.append(source_id)

    if not channels:
        return await message.reply_text("No channels configured.")

    msg = await message.reply_text("🔍 Verifying access...")
    results = ["**Verification Results:**"]

    worker = client

    for chat_id in set(channels):
        try:
            chat = await resolve_chat(worker, chat_id)
            results.append(f"✅ `{chat_id}`: {chat.title}")
        except Exception as e:
            results.append(f"❌ `{chat_id}`: {e}")

    await msg.edit_text("\n".join(results))
