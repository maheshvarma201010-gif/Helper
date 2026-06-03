import re
import asyncio
import cloudscraper
import logging
from bs4 import BeautifulSoup
from pyrogram import Client, filters, enums
from pyrogram.types import Message

logger = logging.getLogger(__name__)

def get_multi_lang_links(target_url: str):
    """
    Blocking scraper logic adapted from user script.
    """
    my_scraper = cloudscraper.create_scraper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
    }

    output = []
    output.append(f"🔍 **Zipper Scan Results**\n`{target_url[:30]}...`\n")

    try:
        response = my_scraper.get(target_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return f"❌ Failed to connect: Status {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')
        languages_found = {}

        # Searching for language download links
        for a_tag in soup.find_all('a', href=True):
            link_text = a_tag.text.lower().strip()
            link_href = a_tag['href']

            if "download" in link_text:
                if "hindi" in link_text:
                    languages_found["Hindi"] = link_href
                elif "tamil" in link_text:
                    languages_found["Tamil"] = link_href
                elif "telugu" in link_text:
                    languages_found["Telugu"] = link_href

        if not languages_found:
            # Fallback: Check if the current page is a direct language page
            # Look for streambeta link in the current page
            streambeta_url = None
            for a_tag in soup.find_all('a', href=True):
                tag_text = a_tag.text.lower().strip()
                tag_href = a_tag['href'].lower().strip()
                if "streambeta" in tag_text or "streambeta" in tag_href:
                    streambeta_url = a_tag['href']
                    break

            if streambeta_url:
                # Infer language from URL or title
                lang_name = "Detected"
                if "/hindi/" in target_url.lower(): lang_name = "Hindi"
                elif "/tamil/" in target_url.lower(): lang_name = "Tamil"
                elif "/telugu/" in target_url.lower(): lang_name = "Telugu"
                languages_found[lang_name] = target_url
            else:
                return "❌ No language download links or StreamBeta endpoints found on this page."

        for lang_name, lang_url in languages_found.items():
            output.append(f"🌐 **Language:** `{lang_name}`")

            headers['Referer'] = target_url
            lang_res = my_scraper.get(lang_url, headers=headers, timeout=15)
            if lang_res.status_code != 200:
                output.append(f"   └ ❌ Failed to open language page.\n")
                continue

            lang_soup = BeautifulSoup(lang_res.text, 'html.parser')
            streambeta_url = None

            for a_tag in lang_soup.find_all('a', href=True):
                tag_text = a_tag.text.lower().strip()
                tag_href = a_tag['href'].lower().strip()
                if "streambeta" in tag_text or "streambeta" in tag_href:
                    streambeta_url = a_tag['href']
                    break

            if not streambeta_url:
                output.append(f"   └ ❌ StreamBeta link not found.\n")
                continue

            headers['Referer'] = lang_url
            beta_res = my_scraper.get(streambeta_url, headers=headers, timeout=15)

            v1_link = "Not Found"
            v2_link = "Not Found"

            if beta_res.status_code == 200:
                beta_soup = BeautifulSoup(beta_res.text, 'html.parser')

                for tag in beta_soup.find_all(['a', 'button']):
                    text_content = tag.text.strip().lower()
                    version_match = re.search(r'(?:v|version|player|server|stream)\s*[-_]?\s*([12])', text_content)

                    if version_match:
                        v_num = version_match.group(1)
                        potential_sources = [
                            tag.get('data-link'), tag.get('data-url'),
                            tag.get('data-href'), tag.get('onclick'), tag.get('href')
                        ]
                        for src in potential_sources:
                            if src and isinstance(src, str) and "javascript" not in src.lower() and src != "#":
                                url_match = re.search(r'(https?://[^\s"\']+)', src)
                                if url_match:
                                    if v_num == "1" and v1_link == "Not Found":
                                        v1_link = url_match.group(1)
                                    elif v_num == "2" and v2_link == "Not Found":
                                        v2_link = url_match.group(1)
                                    break

                all_script_urls = []
                video_indicators = ['workers.dev', 'homelander', 'flashzipper', 'streamwish']

                for script in beta_soup.find_all('script'):
                    if script.string:
                        found_urls = re.findall(r'(https?://[^\s"\']+)', script.string)
                        for url in found_urls:
                            url_clean = url.split('"')[0].split("'")[0].rstrip(';').rstrip('\\')
                            if any(ext in url_clean.lower() for ext in ['.js', '.css', '.png', 'analytics', 'google']):
                                continue
                            if any(ind in url_clean.lower() for ind in video_indicators):
                                if url_clean not in all_script_urls:
                                    all_script_urls.append(url_clean)

                if v1_link == "Not Found" and len(all_script_urls) > 0:
                    v1_link = all_script_urls[0]
                if v2_link == "Not Found" and len(all_script_urls) > 1:
                    v2_link = all_script_urls[1]

            output.append(f"   ├ **v1:** `{v1_link}`")
            output.append(f"   └ **v2:** `{v2_link}`\n")

        return "\n".join(output)

    except Exception as e:
        logger.error(f"Scraper error: {e}")
        return f"❌ Critical Scraper Error: `{str(e)}`"

@Client.on_message(filters.command("b") & filters.private)
async def zipper_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/b <zipper_link>`")

    target_url = message.command[1]
    logger.info(f"Received /b command for URL: {target_url} from user {message.from_user.id}")

    status = await message.reply_text("⏳ **Initializing Zipper Scraper...**\nConnecting to main redirect page...")

    try:
        # Run the blocking scraper in a thread to keep the bot responsive
        result_text = await asyncio.to_thread(get_multi_lang_links, target_url)

        if not result_text:
            result_text = "❌ Error: Scraper returned no content."

        await status.edit_text(result_text, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error handling /b command: {e}")
        await status.edit_text(f"❌ Critical Error: `{e}`")
