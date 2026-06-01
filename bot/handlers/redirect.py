import aiohttp
import logging
from pyrogram import Client, filters
from bot.config import Config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("redirect") & filters.private)
async def redirect_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/redirect <url>`")

    target_url = message.text.split(None, 1)[1]

    # Ensure URL is absolute
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    status_msg = await message.reply_text("🔍 **Following redirects...**")

    try:
        # We use a custom User-Agent to avoid being blocked by some sites
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            # We follow redirects and get the final URL
            # Some sites might require a GET instead of HEAD
            async with session.get(target_url, allow_redirects=True, timeout=15) as response:
                final_url = str(response.url)

                if final_url == target_url and response.status >= 400:
                    await status_msg.edit_text(f"❌ **Error:** Site returned status {response.status}")
                else:
                    await status_msg.edit_text(f"✅ **Final URL:**\n\n`{final_url}`", disable_web_page_preview=True)

    except aiohttp.ClientConnectorError:
        await status_msg.edit_text("❌ **Error:** Could not connect to the server.")
    except aiohttp.InvalidURL:
        await status_msg.edit_text("❌ **Error:** Invalid URL provided.")
    except Exception as e:
        logger.error(f"Redirect error: {e}")
        await status_msg.edit_text(f"❌ **Error:** {str(e)}")
