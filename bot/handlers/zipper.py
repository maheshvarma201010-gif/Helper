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
    Refined scraper logic with strict filtering for Cloudflare Worker streams.
    Only returns v1 and v2 links that match specific security and format signatures.
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

    def is_valid_worker_link(url):
        """Strict verification for Cloudflare Worker streams."""
        if not url or not isinstance(url, str):
            return False
        # Rule: Must contain workers.dev
        if "workers.dev" not in url.lower():
            return False
        # Rule: Must contain base64 signature /ey
        if "/ey" not in url:
            return False
        # Rule: Length must be greater than 150
        if len(url) <= 150:
            return False
        # Rule: Filter fake API links
        if "jikan.moe" in url.lower():
            return False
        return True

    def extract_v1_v2(soup):
        """Two-pass scanning for v1 and v2 links."""
        results = {}

        # Pass 1: HTML elements scan
        for tag in soup.find_all(['a', 'button']):
            txt = tag.text.strip().lower()
            # Only match v1 or v2
            v_match = re.search(r'\bv([12])\b', txt)
            if v_match:
                v_num = v_match.group(1)
                v_key = f"v{v_num}"

                sources = [tag.get('data-link'), tag.get('data-url'), tag.get('data-href'), tag.get('onclick'), tag.get('href')]
                for src in sources:
                    if src and isinstance(src, str) and "javascript" not in src.lower() and src != "#":
                        u_match = re.search(r'(https?://[^\s"\']+)', src)
                        if u_match:
                            candidate = u_match.group(1)
                            if is_valid_worker_link(candidate):
                                if v_key not in results:
                                    results[v_key] = candidate
                                    break

        # Pass 2: Raw script fallback scan
        for script in soup.find_all('script'):
            if script.string:
                clean_script = script.string.replace('\\/', '/')
                found_urls = re.findall(r'https?://[^\s\"\'\\]+', clean_script)
                for u in found_urls:
                    if is_valid_worker_link(u):
                        # Try to associate with v1 or v2 if still missing
                        if "v1" in u.lower() and "v1" not in results:
                            results["v1"] = u
                        elif "v2" in u.lower() and "v2" not in results:
                            results["v2"] = u
                        else:
                            # If no version in URL, find first available of v1 or v2
                            if "v1" not in results: results["v1"] = u
                            elif "v2" not in results: results["v2"] = u

        return results

    # --- EXECUTION ---
    resp = robust_get(target_url)
    if not resp or resp.status_code != 200:
        return f"❌ Failed to connect: Status {getattr(resp, 'status_code', 'Error')}\nURL: `{target_url}`"

    soup = BeautifulSoup(resp.text, 'html.parser')
    current_url = str(resp.url)

    pathways = []
    # Discover language pages
    for a in soup.find_all('a', href=True):
        txt = a.text.lower()
        if "download" in txt:
            if "hindi" in txt: pathways.append(("Hindi", a['href']))
            elif "tamil" in txt: pathways.append(("Tamil", a['href']))
            elif "telugu" in txt: pathways.append(("Telugu", a['href']))

    if not pathways:
        # Check if already on a subpage
        pathways.append(("Detected", current_url))

    output = [f"🔍 **Zipper Scan Results**\n`{target_url[:30]}...`\n"]

    processed_urls = set()
    for label, p_url in pathways:
        if p_url in processed_urls: continue
        processed_urls.add(p_url)

        # Open the specific language page
        p_resp = robust_get(p_url, referer=current_url)
        if not p_resp or p_resp.status_code != 200:
            continue

        p_soup = BeautifulSoup(p_resp.text, 'html.parser')
        p_curr_url = str(p_resp.url)

        # Step 3: Locate the StreamBeta button
        beta_redir = None
        for tag in p_soup.find_all(['a', 'button']):
            txt = tag.text.lower()
            hr = tag.get('href', '')
            oc = tag.get('onclick', '')
            if "streambeta" in txt or "streambeta" in hr.lower() or "streambeta" in oc.lower():
                if hr.startswith("http"): beta_redir = hr
                elif "http" in oc:
                    m = re.search(r'(https?://[^\s"\']+)', oc)
                    if m: beta_redir = m.group(1)
                if beta_redir: break

        # Follow to the StreamBeta player page
        if beta_redir:
            b_resp = robust_get(beta_redir, referer=p_curr_url)
            if b_resp and b_resp.status_code == 200:
                b_soup = BeautifulSoup(b_resp.text, 'html.parser')
                b_curr_url = str(b_resp.url)

                # Handle codedew.com/zipper intermediate hop if present
                if "codedew.com/zipper" in b_curr_url:
                     inner_beta = None
                     for a in b_soup.find_all(['a', 'button']):
                          if "streambeta" in a.text.lower() or "streambeta" in a.get('href', '').lower():
                               inner_beta = a.get('href')
                               if inner_beta: break
                     if inner_beta:
                          b_resp = robust_get(inner_beta, referer=b_curr_url)
                          if b_resp and b_resp.status_code == 200:
                               b_soup = BeautifulSoup(b_resp.text, 'html.parser')

                # Step 4: Final Extraction with 100% Accuracy Rules
                final_links = extract_v1_v2(b_soup)

                if final_links:
                    output.append(f"🌐 **Language:** `{label}`")
                    for v in sorted(final_links.keys()):
                        output.append(f"   ├ **StreamBeta {v} Link:** `{final_links[v]}`")
                    output.append("")

    if len(output) <= 1:
        return "❌ No valid v1/v2 Worker stream links found."

    return "\n".join(output)

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
