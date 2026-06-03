import re
import cloudscraper
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# basic fetching helper to navigate through gateway layers or redirects
def fetch_page(scraper, url, referer=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    if referer:
        headers["Referer"] = referer

    try:
        # primary attempt using automated bypass
        response = scraper.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.text, str(response.url)

        # fallback to follow redirects or bypass 403 blocks
        fb = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
        if fb.status_code == 200:
            if str(fb.url) != url:
                # retry scraper logic on final destination
                r2 = scraper.get(str(fb.url), headers=headers, timeout=15)
                return r2.text, str(r2.url)
            return fb.text, str(fb.url)
    except Exception as e:
        print(f"could not fetch {url}: {e}")
    return None, url

# check if a link is a valid cloudflare worker stream based on length and signature
def is_valid_worker(link):
    if not link or not isinstance(link, str):
        return False
    # rules: must be workers.dev or known host, include /ey signature, and be long enough
    if any(h in link.lower() for h in ["workers.dev", "homelander", "flashzipper", "streamwish", "filepress"]):
        if "/ey" in link and len(link) > 150:
            # block templates or fake paths
            if "${" not in link and "api.jikan.moe" not in link.lower():
                return True
    return False

# scans page elements and raw text to find v1 and v2 links
def scan_content(html, soup):
    results = {}

    # Pass 1: scan html elements (anchors/buttons) for v1 or v2 labels
    for tag in soup.find_all(['a', 'button']):
        txt = tag.text.lower().strip()
        match = re.search(r'\bv([12])\b', txt)
        if match:
            v_key = f"v{match.group(1)}"
            if v_key not in results:
                # check common link attributes
                for attr in ['data-link', 'data-url', 'data-href', 'onclick', 'href']:
                    val = tag.get(attr)
                    if val:
                        u = val.replace('\\/', '/').split('"')[0].split("'")[0].split(',')[0].rstrip(')').strip()
                        if is_valid_worker(u):
                            results[v_key] = u
                            break

    # Pass 2: raw text regex fallback for remaining slots
    if "v1" not in results or "v2" not in results:
        found = re.findall(r'https?://[^\s"\'><)]+', html)
        for m in found:
            u = m.replace('\\/', '/').split('"')[0].split("'")[0].split(',')[0].rstrip(')').strip()
            if is_valid_worker(u):
                if "v1" not in results: results["v1"] = u
                elif "v2" not in results and u not in results.values(): results["v2"] = u

    return results

# locates the next hop link like StreamBeta or Zipper on redirect pages
def find_jump(soup, base_url):
    for tag in soup.find_all(['a', 'button']):
        t = tag.text.lower()
        h = tag.get('href', '')
        o = tag.get('onclick', '')
        if any(x in t or x in h.lower() or x in o.lower() for x in ["streambeta", "stream", "watch", "player", "zipper", "direct"]):
            u = h if h.lower().startswith("http") else urljoin(base_url, h)
            if (not h or h == "#") and "http" in o:
                m = re.search(r'(https?://[^\s"\']+)', o)
                if m: u = m.group(1)
            elif (not h or h == "#") and o:
                m = re.search(r"['\"](\?[^'\"]+)['\"]", o)
                if m: u = urljoin(base_url, m.group(1))
            if u and "http" in u: return u
    return ""

# main logic to start the extraction process
def run_scraper(target_url):
    scraper = cloudscraper.create_scraper()

    html, final_url = fetch_page(scraper, target_url)
    if not html:
        print("error reaching main index")
        return

    soup = BeautifulSoup(html, 'html.parser')

    # discover language sub-links
    hops = []
    for a in soup.find_all('a', href=True):
        txt = a.text.lower().strip()
        if "download" in txt and any(lang in txt for lang in ["hindi", "tamil", "telugu"]):
            if len(txt) < 30 or "archives" in a['href'] or "/hindi/" in a['href']:
                label = "Hindi" if "hindi" in txt else ("Tamil" if "tamil" in txt else "Telugu")
                hops.append((label, urljoin(final_url, a['href'])))

    if not hops:
        hops.append(("StreamBeta", final_url))

    # crawl discovery paths
    processed = set()
    for label, hop_url in hops:
        if hop_url in processed: continue
        processed.add(hop_url)

        p_html, p_url = fetch_page(scraper, hop_url, referer=target_url)
        if not p_html: continue

        streams = scan_content(p_html, BeautifulSoup(p_html, 'html.parser'))

        # recursive jump for redirectors
        curr_h, curr_u = p_html, p_url
        for _ in range(3):
            if streams: break
            jump = find_jump(BeautifulSoup(curr_h, 'html.parser'), curr_u)
            if not jump or jump in processed: break
            processed.add(jump)
            curr_h, curr_u = fetch_page(scraper, jump, referer=curr_u)
            if not curr_h: break
            streams = scan_content(curr_h, BeautifulSoup(curr_h, 'html.parser'))

        if streams:
            print(f"Language: {label}")
            if "v1" in streams: print(f"StreamBeta v1 Link: {streams['v1']}")
            if "v2" in streams: print(f"StreamBeta v2 Link: {streams['v2']}")
            print("")

if __name__ == "__main__":
    # automated target url
    target = "https://codedew.com/zipper/?url=liSDNBKrK%2FJc0qLGY27JrWEbxR3HHTz4ksf1vi0%2BKRFRzh1Vh4ABg3k1rHcbUFaTRHJkvXA4MC51fycs0xH%2BlsLegO9Stc2O0zudgezaiFNXsA%2F7DUpmsy2VA8EaxPb4Uwwj8%2FX5y9JyN13XTe4uRKKwDZ2WiTHo1smgUfR%2Bqzhw1dEk3G%2BOTl3%2Bj2iWVd4%3D"

    run_scraper(target)
