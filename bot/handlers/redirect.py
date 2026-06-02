import aiohttp
import logging
import re
from pyrogram import Client, filters
from bot.config import Config

logger = logging.getLogger(__name__)

# Pattern for basic URL validation
URL_PATTERN = re.compile(
    r'^(?:http|ftp)s?://' # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
    r'localhost|' #localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
    r'(?::\d+)?' # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

@Client.on_message(filters.command("redirect") & filters.private)
async def redirect_command(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/redirect <url>`")

    target_url = message.text.split(None, 1)[1].strip()

    # Simple validation
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    if not URL_PATTERN.match(target_url):
        return await message.reply_text("❌ Invalid URL format.")

    status_msg = await message.reply_text("🔍 **Following redirect chain...**")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        # Using a session to follow redirects automatically
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(target_url, allow_redirects=True, timeout=20) as response:
                final_url = str(response.url)

                # Check if we actually moved or if it's a dead end
                if response.status >= 400 and final_url == target_url:
                     return await status_msg.edit_text(f"❌ Site returned error: {response.status}")

                await status_msg.edit_text(f"`{final_url}`", disable_web_page_preview=True)

    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ Request timed out.")
    except aiohttp.ClientConnectorError as e:
        await status_msg.edit_text(f"❌ Connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Redirect error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
