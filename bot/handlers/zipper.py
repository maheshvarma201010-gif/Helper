import re
import asyncio
import cloudscraper
import requests
import logging
from bs4 import BeautifulSoup
from pyrogram import Client, filters, enums
from pyrogram.types import Message

logger = logging.getLogger(__name__)

def get_multi_lang_links(target_url: str):
    """
    Blocking scraper logic adapted from user script.
    """
    # Create a more robust scraper instance
    my_scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'android',
            'mobile': True
        }
    )

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    output = []
    output.append(f"🔍 **Zipper Scan Results**\n`{target_url[:30]}...`\n")

    try:
        response = my_scraper.get(target_url, headers=headers, timeout=20)

        # Fallback logic for redirects if initial request fails (e.g., 403 on redirector)
        if response.status_code != 200:
            try:
                fb_res = requests.get(target_url, headers=headers, allow_redirects=True, timeout=15)
                if fb_res.status_code == 200:
                    if str(fb_res.url) != target_url:
                        target_url = str(fb_res.url)
                        response = my_scraper.get(target_url, headers=headers, timeout=20)
                    else:
                        response = fb_res
            except Exception as fe:
                logger.error(f"Redirect fallback error: {fe}")

        if response.status_code != 200:
            return f"❌ Failed to connect to main page: Status {response.status_code}\nURL: `{target_url}`"

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
            for a_tag in soup.find_all(['a', 'button']):
                tag_text = a_tag.text.lower().strip()
                tag_href = a_tag.get('href', '').lower().strip()
                tag_onclick = a_tag.get('onclick', '').lower().strip()

                if any(x in tag_text or x in tag_href or x in tag_onclick for x in ["streambeta", "stream", "watch", "player"]):
                    if "http" in tag_href:
                        streambeta_url = a_tag['href']
                    elif "http" in tag_onclick:
                        match = re.search(r'(https?://[^\s"\']+)', tag_onclick)
                        if match: streambeta_url = match.group(1)
                    if streambeta_url: break

            if not streambeta_url:
                iframe = soup.find('iframe', src=re.compile(r'streambeta|player|stream'))
                if iframe: streambeta_url = iframe['src']

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
            try:
                lang_res = my_scraper.get(lang_url, headers=headers, timeout=20)
                if lang_res.status_code != 200:
                    output.append(f"   └ ❌ Failed to open language page (Status {lang_res.status_code}).\n")
                    continue
            except Exception as e:
                output.append(f"   └ ❌ Error opening language page: `{str(e)[:50]}`\n")
                continue

            lang_soup = BeautifulSoup(lang_res.text, 'html.parser')
            streambeta_url = None

            for a_tag in lang_soup.find_all(['a', 'button'], href=True):
                tag_text = a_tag.text.lower().strip()
                tag_href = a_tag.get('href', '').lower().strip()
                tag_onclick = a_tag.get('onclick', '').lower().strip()

                if any(x in tag_text or x in tag_href or x in tag_onclick for x in ["streambeta", "stream", "watch", "player"]):
                    if "http" in tag_href:
                        streambeta_url = a_tag['href']
                    elif "http" in tag_onclick:
                        match = re.search(r'(https?://[^\s"\']+)', tag_onclick)
                        if match: streambeta_url = match.group(1)

                    if streambeta_url: break

            if not streambeta_url:
                # Last resort: look for iframes
                iframe = lang_soup.find('iframe', src=re.compile(r'streambeta|player|stream'))
                if iframe:
                    streambeta_url = iframe['src']

            if not streambeta_url:
                output.append(f"   └ ❌ StreamBeta/Player link not found.\n")
                continue

            headers['Referer'] = lang_url
            try:
                beta_res = my_scraper.get(streambeta_url, headers=headers, timeout=20)
            except Exception as e:
                output.append(f"   └ ❌ Error opening StreamBeta page: `{str(e)[:50]}`\n")
                continue

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
                video_indicators = ['workers.dev', 'homelander', 'flashzipper', 'streamwish', 'filepress', 'gdflix', 'streamtape']

                # Check for iframes in beta page
                for iframe in beta_soup.find_all('iframe', src=True):
                    if any(ind in iframe['src'].lower() for ind in video_indicators):
                        all_script_urls.append(iframe['src'])

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
