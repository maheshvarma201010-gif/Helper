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
    Robust scraper logic with redirect fallback and dynamic version extraction.
    Designed to handle multi-level redirectors (RareAnimes, AnimeToonHindi, codedew).
    """
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'android',
            'mobile': True
        }
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    def robust_get(url, referer=None):
        if referer:
            headers['Referer'] = referer
        else:
            headers.pop('Referer', None)

        try:
            resp = scraper.get(url, headers=headers, timeout=20)
            if resp.status_code == 200:
                return resp

            logger.info(f"Scraper got {resp.status_code} for {url}. Trying requests fallback...")
            fb_res = requests.get(url, headers=headers, allow_redirects=True, timeout=15)

            if fb_res.status_code == 200:
                if str(fb_res.url) != url:
                    logger.info(f"Redirected to {fb_res.url}. Retrying scraper on final URL...")
                    return scraper.get(str(fb_res.url), headers=headers, timeout=20)
                return fb_res
            return resp
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            try:
                return requests.get(url, headers=headers, allow_redirects=True, timeout=15)
            except:
                return None

    def extract_from_page(soup):
        """Extracts all possible video links and versioned buttons from a page."""
        results = {}
        indicators = ['workers.dev', 'homelander', 'flashzipper', 'streamwish', 'filepress', 'gdflix', 'streamtape', 'pixeldra.in', 'filepress']

        # 1. Elements (a, button)
        for tag in soup.find_all(['a', 'button']):
            txt = tag.text.strip().lower()
            v_match = re.search(r'(?:v|version|player|server|stream|mirror)\s*[-_]?\s*(\d+)', txt)
            v_key = f"v{v_match.group(1)}" if v_match else None

            is_video_btn = any(x in txt for x in ["streambeta", "watch", "download", "player", "mirror", "server", "v1", "v2"])
            if not v_key and is_video_btn: v_key = "v1"

            if v_key:
                sources = [tag.get('data-link'), tag.get('data-url'), tag.get('data-href'), tag.get('onclick'), tag.get('href')]
                for src in sources:
                    if src and isinstance(src, str) and "javascript" not in src.lower() and src != "#":
                        u_match = re.search(r'(https?://[^\s"\']+)', src)
                        if u_match:
                            u = u_match.group(1)
                            uvm = re.search(r'v(\d+)', u.lower())
                            vk = f"v{uvm.group(1)}" if uvm else v_key
                            if vk not in results:
                                results[vk] = u
                                break

        # 2. Scripts and Iframes
        all_text = str(soup).replace('\\/', '/')
        found_urls = re.findall(r'https?://[^\s\"\'\\]+', all_text)
        for u in found_urls:
            if any(ind in u.lower() for ind in indicators):
                vm = re.search(r'v(\d+)', u.lower())
                vk = f"v{vm.group(1)}" if vm else None
                if vk:
                    if vk not in results: results[vk] = u
                else:
                    for i in range(1, 21):
                        slot = f"v{i}"
                        if slot not in results:
                            results[slot] = u
                            break
        return results

    # --- MAIN FLOW ---
    output = [f"🔍 **Zipper Scan Results**\n`{target_url[:30]}...`\n"]

    resp = robust_get(target_url)
    if not resp or resp.status_code != 200:
        return f"❌ Failed to connect: Status {getattr(resp, 'status_code', 'Error')}\nURL: `{target_url}`"

    soup = BeautifulSoup(resp.text, 'html.parser')
    current_url = str(resp.url)

    pathways = []
    # RareAnimes Style (Language Links)
    for a in soup.find_all('a', href=True):
        txt = a.text.lower()
        if "download" in txt:
            if "hindi" in txt: pathways.append(("Hindi", a['href']))
            elif "tamil" in txt: pathways.append(("Tamil", a['href']))
            elif "telugu" in txt: pathways.append(("Telugu", a['href']))

    # Strategy 2: Direct links or redirectors
    for tag in soup.find_all(['a', 'button']):
        txt = tag.text.strip()
        hr = tag.get('href', '')
        oc = tag.get('onclick', '')
        if any(x in txt.lower() or x in hr.lower() or x in oc.lower() for x in ["streambeta", "stream", "watch", "player", "zipper", "multiquality", "direct"]):
            u = hr if (hr and hr.startswith("http")) else (re.search(r'(https?://[^\s"\']+)', oc).group(1) if "http" in oc else None)
            if u: pathways.append((txt if (txt and len(txt) < 30) else "Watch", u))

    if not pathways:
        pathways.append(("Detected", current_url))

    processed_urls = set()
    for label, p_url in pathways:
        if p_url in processed_urls: continue
        processed_urls.add(p_url)

        # Filter out social links
        if any(x in p_url for x in ["facebook.com", "twitter.com", "instagram.com", "google.com", "youtube.com"]):
             continue

        # Fetch pathway page
        p_resp = robust_get(p_url, referer=current_url)
        if not p_resp or p_resp.status_code != 200:
            continue

        p_soup = BeautifulSoup(p_resp.text, 'html.parser')
        p_curr_url = str(p_resp.url)

        # Try extraction
        v_links = extract_from_page(p_soup)

        # Follow hops if no video links found yet
        if not v_links:
            potential_next = []
            for a in p_soup.find_all(['a', 'button']):
                txt_l = a.text.lower()
                hr = a.get('href', '')
                oc = a.get('onclick', '')
                if any(x in txt_l or x in hr.lower() or x in oc.lower() for x in ["streambeta", "stream", "watch", "player", "zipper", "multiquality"]):
                    u = hr if (hr and hr.startswith("http")) else (re.search(r'(https?://[^\s"\']+)', oc).group(1) if "http" in oc else None)
                    if u and u not in processed_urls: potential_next.append(u)

            for next_url in potential_next[:3]:
                n_resp = robust_get(next_url, referer=p_curr_url)
                if n_resp and n_resp.status_code == 200:
                    n_soup = BeautifulSoup(n_resp.text, 'html.parser')
                    v_links.update(extract_from_page(n_soup))

        # Resolve redirectors (follow codedew to get workers.dev links)
        final_links = {}
        indicators = ['workers.dev', 'homelander', 'flashzipper', 'streamwish', 'filepress', 'gdflix', 'streamtape', 'pixeldra.in']

        for vk, vu in v_links.items():
            if any(ind in vu.lower() for ind in indicators):
                 final_links[vk] = vu
            elif "codedew.com" in vu:
                 r_resp = robust_get(vu, referer=p_curr_url)
                 if r_resp and r_resp.status_code == 200:
                      r_soup = BeautifulSoup(r_resp.text, 'html.parser')
                      # If this resolved page is ANOTHER redirector (zipper), follow it once more
                      if "codedew.com/zipper" in str(r_resp.url):
                           # Look for next hop
                           next_h = None
                           for a in r_soup.find_all(['a', 'button']):
                                if any(x in a.text.lower() or x in a.get('href', '').lower() for x in ["streambeta", "stream", "watch"]):
                                     next_h = a.get('href')
                                     if next_h: break
                           if next_h:
                                r_resp = robust_get(next_h, referer=str(r_resp.url))
                                if r_resp and r_resp.status_code == 200:
                                     r_soup = BeautifulSoup(r_resp.text, 'html.parser')

                      rv_links = extract_from_page(r_soup)
                      for rk, ru in rv_links.items():
                           if any(ind in ru.lower() for ind in indicators):
                                key = vk if vk != "v1" else rk
                                if key not in final_links: final_links[key] = ru

        if final_links:
            output.append(f"🌐 **Language/Section:** `{label}`")
            for v in sorted(final_links.keys(), key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 99):
                output.append(f"   ├ **{v}:** `{final_links[v]}`")
            output.append("")

    if len(output) <= 1:
        return "❌ No video links discovered after scanning pathways."

    return "\n".join(output)

@Client.on_message(filters.command("b") & filters.private)
async def zipper_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/b <zipper_link>`")

    target_url = message.command[1]
    logger.info(f"Received /b command for URL: {target_url} from user {message.from_user.id}")

    status = await message.reply_text("⏳ **Initializing Zipper Scraper...**\nConnecting to main redirect page...")

    try:
        result_text = await asyncio.to_thread(get_multi_lang_links, target_url)
        if not result_text:
            result_text = "❌ Error: Scraper returned no content."
        await status.edit_text(result_text, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error handling /b command: {e}")
        await status.edit_text(f"❌ Critical Error: `{e}`")
