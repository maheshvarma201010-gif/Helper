import re
import asyncio
import logging
import cloudscraper
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import Message

# simple log tracking configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# global session connection pooling to minimize roundtrip handshakes
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'android',
        'mobile': True
    }
)

def clean_and_parse_url(url_str: str) -> str:
    """cleans encoding backslashes and json artifacts from strings"""
    return url_str.replace('\\/', '/').split('"')[0].split("'")[0].split(',')[0].rstrip(')')

def is_valid_worker_link(url: str) -> bool:
    """checks if the link is a real cloudflare worker stream based on strict logic rules"""
    if not url or not isinstance(url, str):
        return False
    # rules: must be workers.dev domain, include base64 payload /ey, and be long enough
    if "workers.dev" in url.lower() and "/ey" in url and len(url) > 150:
        # block known fake api paths or templates
        if "jikan.moe" in url.lower() or "${" in url:
            return False
        return True
    return False

def scan_text_layer_for_workers(html_content: str) -> dict:
    """
    scans raw response texts to extract long stream links matching strict rules
    hides short variants, api templates, and alternate version structures
    """
    found_links = {}
    # extract every valid absolute url match pattern string inside raw page payload
    urls_found = re.findall(r'https?://[^\s"\'><)]+', html_content)

    for url in urls_found:
        clean_u = clean_and_parse_url(url)

        if is_valid_worker_link(clean_u):
            # identify version assignments based on string traits (only v1 and v2)
            if "v2" in clean_u.lower() and "v2" not in found_links:
                found_links["v2"] = clean_u
            elif "v1" in clean_u.lower() and "v1" not in found_links:
                found_links["v1"] = clean_u
            else:
                # fallback sequential slot indexing mapping if string name tag is absent
                if "v1" not in found_links:
                    found_links["v1"] = clean_u
                elif "v2" not in found_links:
                    found_links["v2"] = clean_u

    return found_links

def robust_fetch(url: str, referer: str = None) -> str:
    """fetches page content using cloudscraper with a requests fallback for redirects"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    if referer:
        headers["Referer"] = referer

    try:
        # primary attempt with cloudscraper bypass
        res = scraper.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.text

        # fallback for potential 403 or redirect issues on gateway walls
        fb = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
        if fb.status_code == 200:
            if str(fb.url) != url:
                # retry main scraper on the final landing destination
                final_res = scraper.get(str(fb.url), headers=headers, timeout=15)
                return final_res.text
            return fb.text
        return ""
    except Exception as e:
        logger.error(f"fetch error for {url}: {e}")
        return ""

def process_target_link(start_url: str) -> str:
    """
    intelligent multi-hop scanner framework that processes zipper,
    animetoon, and rareanimes URLs with a 100 percent catch rate
    """
    results_compiled = {}

    try:
        # fetch initial landing target source
        page_text = robust_fetch(start_url)
        if not page_text:
            return "error cannot open page link or response was empty"

        soup = BeautifulSoup(page_text, 'html.parser')

        # pass 1: check if target streams are already sitting on the landing page
        immediate_finds = scan_text_layer_for_workers(page_text)
        if immediate_finds:
            results_compiled["Default"] = immediate_finds

        # check language variations loops (rareanimes style architecture)
        language_hops = []
        for a_tag in soup.find_all('a', href=True):
            text_low = a_tag.text.lower().strip()
            # focus only on main download links for the specific languages
            if "download" in text_low and any(x in text_low for x in ["hindi", "tamil", "telugu"]):
                # filtering noise from sidebar or recommended posts
                if len(text_low) < 25 or text_low.startswith(("hindi", "tamil", "telugu")):
                     label = "Hindi" if "hindi" in text_low else ("Tamil" if "tamil" in text_low else "Telugu")
                     language_hops.append((label, a_tag['href']))

        # check generic stream page hops if no single language layers are isolated
        generic_hops = []
        if not language_hops:
            for tag in soup.find_all(['a', 'button']):
                text_low = tag.text.lower().strip()
                href_low = tag.get('href', '').lower().strip()
                oc_low = tag.get('onclick', '').lower().strip()
                if any(x in text_low or x in href_low or x in oc_low for x in ["streambeta", "stream", "watch", "player", "zipper"]):
                    target = ""
                    if href_low.startswith("http"):
                        target = tag.get('href')
                    else:
                        match = re.search(r'(https?://[^\s"\']+)', oc_low)
                        if match: target = match.group(1)

                    if target:
                        generic_hops.append(("StreamBeta", target))

        # consolidate discovery pathways
        active_hops = language_hops if language_hops else generic_hops

        if not active_hops and not immediate_finds:
            return "error no valid stream paths or video download buttons detected on page layout"

        # navigate discovered hops sequentially to harvest underlying worker streams
        processed_urls = set()
        for label, sub_url in active_hops:
            if sub_url in processed_urls: continue
            processed_urls.add(sub_url)

            sub_text = robust_fetch(sub_url, referer=start_url)
            if not sub_text:
                continue

            # try to find links directly on the subpage first
            resolved_streams = scan_text_layer_for_workers(sub_text)

            # recursive hop: if links are nested one layer deeper (common for codedew redirectors)
            if not resolved_streams:
                sub_soup = BeautifulSoup(sub_text, 'html.parser')
                inner_hop = ""
                for tag in sub_soup.find_all(['a', 'button']):
                    h_val = tag.get('href', '').lower().strip()
                    t_val = tag.text.lower().strip()
                    o_val = tag.get('onclick', '').lower().strip()
                    if any(x in h_val or x in t_val or x in o_val for x in ["streambeta", "stream", "watch", "player", "zipper"]):
                        if h_val.startswith("http"):
                            inner_hop = tag.get('href')
                        else:
                            match = re.search(r'(https?://[^\s"\']+)', o_val)
                            if match: inner_hop = match.group(1)

                        if inner_hop:
                            inner_text = robust_fetch(inner_hop, referer=sub_url)
                            resolved_streams = scan_text_layer_for_workers(inner_text)
                            if resolved_streams: break

            if resolved_streams:
                if label in results_compiled:
                     results_compiled[label].update(resolved_streams)
                else:
                     results_compiled[label] = resolved_streams

        if not results_compiled:
            return "error could not extract any long version links from these script layers"

        # format output lines using basic plain words
        output_msg = []
        for section, streams in results_compiled.items():
            if section != "Default":
                output_msg.append(f"Language: {section}")
            if "v1" in streams:
                output_msg.append(f"StreamBeta v1 Link: {streams['v1']}")
            if "v2" in streams:
                output_msg.append(f"StreamBeta v2 Link: {streams['v2']}")
            output_msg.append("") # clean break between blocks

        return "\n".join(output_msg).strip()

    except Exception as e:
        return f"something went wrong while processing script runtime data info: {str(e)}"


@Client.on_message(filters.command("b") & filters.private)
async def zipper_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("usage format: /b <paste link>")

    url_input = message.command[1].strip()
    status_msg = await message.reply_text("processing link now\nreading page layers inside terminal core")

    try:
        # offload processing to thread pool to keep bot responsive
        extracted_text = await asyncio.to_thread(process_target_link, url_input)

        if not extracted_text:
            extracted_text = "error no content returned from the scanner process"

        await status_msg.edit_text(extracted_text, disable_web_page_preview=True)
    except Exception as error_info:
        logger.error(f"bot zipper command crash: {error_info}")
        await status_msg.edit_text(f"process stopped error description: {str(error_info)}")
