import re

def extract_metadata(text):
    if not text:
        return None, None, None, ""

    # Quality extraction
    qualities = ["2160p", "1440p", "1080p", "900p", "720p", "576p", "540p", "480p", "360p", "240p"]
    quality = None
    for q in qualities:
        if q in text:
            quality = q
            break
    if not quality:
        for q in qualities:
            if q.lower() in text.lower():
                quality = q
                break

    # Season extraction
    season_patterns = [
        r'Season\s*(\d+)',
        r'S(\d+)',
        r'(\d+)x\d+'
    ]
    season = None
    for pattern in season_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            season = int(match.group(1))
            break

    # Episode extraction
    episode_patterns = [
        r'Episode\s*(\d+)',
        r'EP(\d+)',
        r'E(\d+)',
        r'S\d+E(\d+)',
        r'\d+x(\d+)',
        r'(?:\s|\[|-)(\d{1,4})(?:\s|\]|\.|$)'
    ]
    episode = None
    for pattern in episode_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Avoid matching year like 2024 as episode
            val = int(match.group(1))
            if val < 2000:
                episode = val
                break

    # Title extraction
    clean_text = text
    patterns_to_remove = [
        r'\.(?:mkv|mp4|avi|mp3|zip|rar)$',
        r'\[.*?\]',
        r'\(.*?\)',
        r'(?:Season|S)\s*\d+',
        r'(?:Episode|EP|E)\s*\d+',
        r'\d+x\d+',
        r'(?:2160p|1440p|1080p|900p|720p|576p|540p|480p|360p|240p)',
        r'(?:x264|x265|10bit|WEB-DL|BluRay|Multi Audio|ESub|Dual|DUB|Multi|Hin|Tam|Tel|Jap|English)',
    ]
    for pattern in patterns_to_remove:
        clean_text = re.sub(pattern, ' ', clean_text, flags=re.IGNORECASE)

    clean_text = clean_text.replace('-', ' ').replace('_', ' ').replace('.', ' ').replace(':', ' ')
    title = ' '.join(clean_text.split()).strip()

    return season, episode, quality, title

def get_metadata(caption, filename):
    # Priority 1: Caption
    s, e, q, t = extract_metadata(caption)

    # Priority 2: Filename (if metadata missing from caption)
    s_f, e_f, q_f, t_f = extract_metadata(filename)

    # Strict Priority Logic
    final_s = s if s is not None else s_f
    final_e = e if e is not None else e_f
    final_q = q if q is not None else q_f

    # Priority 3: Fallback
    if final_s is None: final_s = 1
    if final_e is None: final_e = 0
    if final_q is None: final_q = "Unknown"

    final_title = t if len(t) > 2 else t_f

    return final_s, final_e, final_q, final_title
