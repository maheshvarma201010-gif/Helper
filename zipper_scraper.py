import re
import cloudscraper
import requests
from bs4 import BeautifulSoup

# basic fetch helper to handle potential blocks or redirects
def fetch_page(scraper, url, referer=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
    }
    if referer:
        headers["Referer"] = referer

    try:
        # try cloudscraper first
        response = scraper.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response

        # fallback to standard requests for redirect following
        fb = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
        if fb.status_code == 200:
            if str(fb.url) != url:
                # retry scraper on final destination
                return scraper.get(str(fb.url), headers=headers, timeout=15)
            return fb
        return response
    except Exception as e:
        print(f"error fetching {url}: {e}")
        return None

# check if the link is a valid cloudflare worker stream
def is_valid_worker(url):
    if not url:
        return False
    # rules: workers.dev domain, /ey base64 signature, and length over 150
    if "workers.dev" in url and "/ey" in url and len(url) > 150:
        if "jikan.moe" not in url:
            return True
    return False

# main extraction logic
def extract_anime_links(index_url):
    scraper = cloudscraper.create_scraper()

    # 1. request the main page
    response = fetch_page(scraper, index_url)
    if not response or response.status_code != 200:
        print("failed to reach the index page")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    current_url = str(response.url)

    # 2. find language sections (hindi, tamil, telugu)
    pathways = {}
    for a in soup.find_all("a", href=True):
        text = a.text.lower()
        href = a["href"]
        if "download" in text:
            if "hindi" in text: pathways["Hindi"] = href
            elif "tamil" in text: pathways["Tamil"] = href
            elif "telugu" in text: pathways["Telugu"] = href

    if not pathways:
        # assume current page might be the subpage
        pathways["Detected"] = current_url

    # 3. process each language section
    for lang, lang_url in pathways.items():
        # request the language page
        lang_res = fetch_page(scraper, lang_url, referer=current_url)
        if not lang_res or lang_res.status_code != 200:
            continue

        lang_soup = BeautifulSoup(lang_res.text, "html.parser")
        lang_final_url = str(lang_res.url)

        # find the streambeta player link
        streambeta_url = None
        for tag in lang_soup.find_all(["a", "button"]):
            tag_text = tag.text.lower()
            tag_href = tag.get("href", "")
            tag_onclick = tag.get("onclick", "")
            if "streambeta" in tag_text or "streambeta" in tag_href.lower() or "streambeta" in tag_onclick.lower():
                if tag_href.startswith("http"):
                    streambeta_url = tag_href
                elif "http" in tag_onclick:
                    match = re.search(r"(https?://[^\s\"']+)", tag_onclick)
                    if match: streambeta_url = match.group(1)
                if streambeta_url: break

        if not streambeta_url:
            continue

        # request the streambeta page
        beta_res = fetch_page(scraper, streambeta_url, referer=lang_final_url)
        if not beta_res or beta_res.status_code != 200:
            continue

        beta_soup = BeautifulSoup(beta_res.text, "html.parser")
        beta_final_url = str(beta_res.url)

        # handle intermediate redirector pages if they exist
        if "codedew.com/zipper" in beta_final_url:
            inner_link = None
            for a in beta_soup.find_all("a", href=True):
                if "streambeta" in a.text.lower() or "streambeta" in a["href"].lower():
                    inner_link = a["href"]
                    break
            if inner_link:
                beta_res = fetch_page(scraper, inner_link, referer=beta_final_url)
                if beta_res:
                    beta_soup = BeautifulSoup(beta_res.text, "html.parser")

        # 4. final extraction with two-pass scanning
        mapped_links = {}

        # pass 1: scan html elements for v1/v2
        for tag in beta_soup.find_all(["a", "button"]):
            text = tag.text.strip().lower()
            # only look for v1 and v2
            match = re.search(r"\bv([12])\b", text)
            if match:
                v_key = f"v{match.group(1)}"
                # check common attributes for the url
                attrs = ["data-link", "data-url", "data-href", "onclick", "href"]
                for attr in attrs:
                    val = tag.get(attr)
                    if val and isinstance(val, str) and "http" in val:
                        url_match = re.search(r"(https?://[^\s\"']+)", val)
                        if url_match:
                            candidate = url_match.group(1)
                            if is_valid_worker(candidate):
                                if v_key not in mapped_links:
                                    mapped_links[v_key] = candidate
                                    break

        # pass 2: raw script block regex fallback
        for script in beta_soup.find_all("script"):
            if script.string:
                # unescape slashes in script content
                script_content = script.string.replace("\\/", "/")
                found = re.findall(r"https?://[^\s\"\'\\]+", script_content)
                for link in found:
                    if is_valid_worker(link):
                        # assign to v1 or v2 based on url content or availability
                        if "v1" in link.lower() and "v1" not in mapped_links:
                            mapped_links["v1"] = link
                        elif "v2" in link.lower() and "v2" not in mapped_links:
                            mapped_links["v2"] = link
                        else:
                            if "v1" not in mapped_links: mapped_links["v1"] = link
                            elif "v2" not in mapped_links: mapped_links["v2"] = link

        # display results for this language
        if mapped_links:
            if "v1" in mapped_links:
                print(f"StreamBeta v1 Link: {mapped_links['v1']}")
            if "v2" in mapped_links:
                print(f"StreamBeta v2 Link: {mapped_links['v2']}")

if __name__ == "__main__":
    # index url for the movie
    target = "https://codedew.com/zipper/?url=liSDNBKrK%2FJc0qLGY27JrWEbxR3HHTz4ksf1vi0%2BKRFRzh1Vh4ABg3k1rHcbUFaTRHJkvXA4MC51fycs0xH%2BlsLegO9Stc2O0zudgezaiFNXsA%2F7DUpmsy2VA8EaxPb4Uwwj8%2FX5y9JyN13XTe4uRKKwDZ2WiTHo1smgUfR%2Bqzhw1dEk3G%2BOTl3%2Bj2iWVd4%3D"

    # start the extraction process
    extract_anime_links(target)
