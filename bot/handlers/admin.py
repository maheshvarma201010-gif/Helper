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
        # Attempt to cache immediately
        try:
            await client.get_chat(channel_id)
            if client.userbot:
                await client.userbot.get_chat(channel_id)
        except:
            pass
        await message.reply_text("Source channel updated successfully and cached.")
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
    if not (hasattr(client, "userbot") and client.userbot and client.userbot.is_connected):
        return await message.reply_text("❌ Userbot is not active. Indexing requires Userbot.")

    source_id = await db.get_source_channel()
    if not source_id:
        return await message.reply_text("Source channel not set. Use /setchannel first.")

    progress = await message.reply_text("Starting indexing...")
    count = await index_channel(client.userbot, source_id, progress)

    if count >= 0:
        await progress.edit_text(f"Indexing complete! Added {count} messages.")
    else:
        await progress.edit_text("Indexing failed. Check logs.")

@Client.on_message(filters.command("verify") & filters.user(Config.ADMINS))
async def verify_command(client, message):
    """Verifies access to all configured channels and caches them."""
    source_id = await db.get_source_channel()
    channels = set(Config.REPLACE_TEXT_CHANNELS)
    if source_id:
        channels.add(source_id)

    if not channels:
        return await message.reply_text("No channels configured to verify.")

    results = ["**Channel Access Verification:**"]
    for chat_id in channels:
        bot_access = "✅"
        userbot_access = "✅" if client.userbot else "❌ (Userbot Off)"

        try:
            await client.get_chat(chat_id)
        except Exception as e:
            bot_access = f"❌ ({e})"

        if client.userbot:
            try:
                await client.userbot.get_chat(chat_id)
            except Exception as e:
                userbot_access = f"❌ ({e})"

        results.append(f"Chat `{chat_id}`:\n  Bot: {bot_access}\n  Userbot: {userbot_access}")

    await message.reply_text("\n\n".join(results))
