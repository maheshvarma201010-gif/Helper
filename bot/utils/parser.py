import re

def extract_metadata(text):
    if not text:
        return 1, 0, "Unknown", ""

    # Quality extraction - Expanded list
    qualities = ["2160p", "1440p", "1080p", "900p", "720p", "576p", "540p", "480p", "360p", "240p", "BluRay", "WEB-DL"]
    quality = "Unknown"
    for q in qualities:
        if q.lower() in text.lower():
            # Standardize quality string
            quality = q if "p" in q else quality
            if quality == "Unknown" and ("BluRay" in q or "WEB-DL" in q):
                 # Try to find a 'p' quality near these tags if not found yet
                 pass

    # Season extraction - Support more patterns like 'S22', 'Season 22', '22x01'
    season_match = re.search(r'(?:Season|S)\s*(\d+)', text, re.IGNORECASE)
    if not season_match:
        season_match = re.search(r'(\d+)x\d+', text, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else 1

    # Episode extraction - Support 'E1135', 'EP1135', '1135', 'S22E1135'
    episode_match = re.search(r'(?:Episode|EP|E|S\d+E)\s*(\d+)', text, re.IGNORECASE)
    if not episode_match:
        episode_match = re.search(r'\d+x(\d+)', text, re.IGNORECASE)
    if not episode_match:
        # Match standalone numbers that look like episodes (3-4 digits usually for long series)
        episode_match = re.search(r'(?:\s|-|\[)(\d{1,4})(?:\s|\]|\.|$)', text)

    episode = int(episode_match.group(1)) if episode_match else 0

    # Title extraction - Aggressive cleaning
    clean_text = text
    # Remove metadata patterns
    patterns_to_remove = [
        r'\.(?:mkv|mp4|avi|mp3|zip|rar)$',
        r'\[.*?\]',
        r'\(.*?\)',
        r'(?:Season|S)\s*\d+',
        r'(?:Episode|EP|E)\s*\d+',
        r'\d+x\d+',
        r'(?:2160p|1440p|1080p|900p|720p|576p|540p|480p|360p|240p)',
        r'(?:x264|x265|10bit|WEB-DL|BluRay|Multi Audio|ESub|Dual|DUB|Multi|Hin|Tam|Tel|Jap|English)',
        r'(?:💾 Size :.*?|🌍 Languages :.*?|📺 Quality :.*?)'
    ]
    for pattern in patterns_to_remove:
        clean_text = re.sub(pattern, ' ', clean_text, flags=re.IGNORECASE | re.DOTALL)

    clean_text = clean_text.replace('-', ' ').replace('_', ' ').replace('.', ' ').replace(':', ' ')
    title = ' '.join(clean_text.split()).strip()

    # Fallback title if everything was stripped
    if not title or len(title) < 2:
        title = text.split('.')[0][:50].strip()

    return season, episode, quality, title

def get_metadata(caption, filename):
    s_c, e_c, q_c, t_c = extract_metadata(caption)
    s_f, e_f, q_f, t_f = extract_metadata(filename)

    # Selection logic: prioritize the most complete info
    s = s_c if s_c != 1 else s_f
    e = e_c if e_c != 0 else s_f if e_c == 0 and s_f > 100 else e_f # Handle cases where ep is misidentified as season
    q = q_c if q_c != "Unknown" else q_f
    t = t_f if len(t_f) > len(t_c) else t_c

    return s, e, q, t
