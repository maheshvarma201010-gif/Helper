from pyrogram import Client, filters
from bot.utils.search_engine import search_files
from bot.database.mongo import db

@Client.on_message(filters.command("search") & filters.private)
async def search_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /search <title>")

    query = message.text.split(None, 1)[1]
    grouped_results, title, season = await search_files(query)

    if not any(grouped_results.values()):
        return await message.reply_text("No results found.")

    batch_bot = await db.get_batch_bot() or "DeepLinkBot"
    source_channel = await db.get_source_channel()
    # Normalize source_channel ID for link (remove -100)
    channel_link_id = str(source_channel).replace("-100", "") if source_channel else "channelid"

    response_text = f"📂 {title.title()}"
    if season:
        response_text += f" Season {season}"

    total_files = 0

    # Process by priority: 480p, 720p, 1080p, 2160p
    for quality in ["480p", "720p", "1080p", "2160p"]:
        items = grouped_results.get(quality, [])
        if items:
            total_files += len(items)
            # Find range
            msg_ids = sorted([i["message_id"] for i in items])
            first_id = msg_ids[0]
            last_id = msg_ids[-1]

            response_text += f"\n\n📺 {quality.upper()}:\n"
            response_text += f"https://t.me/{batch_bot}?start=batch_{quality}_{first_id}_{last_id}\n"

            # Add batch range link
            response_text += f"📦 Batch Range:\n/batch https://t.me/c/{channel_link_id}/{first_id}-{last_id}"

    if grouped_results.get("Unknown"):
         response_text += f"\n\n📺 UNKNOWN:\nTotal Files: {len(grouped_results['Unknown'])}"
         total_files += len(grouped_results['Unknown'])

    response_text += f"\n\nTotal Files: {total_files}"

    await message.reply_text(response_text, disable_web_page_preview=True)
