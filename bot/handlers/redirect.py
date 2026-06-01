from pyrogram import Client, filters
from bot.config import Config
import urllib.parse

@Client.on_message(filters.command("redirect") & filters.private)
async def redirect_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/redirect <url>`")

    target_url = message.text.split(None, 1)[1]

    # Ensure URL is absolute
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # Encode the target URL
    encoded_url = urllib.parse.quote(target_url, safe='')

    # Generate the redirect link
    redirect_link = f"{Config.BASE_URL}/go?url={encoded_url}"

    await message.reply_text(
        f"🔗 **Redirect Link Generated:**\n\n`{redirect_link}`",
        disable_web_page_preview=True
    )
