import re

def extract_metadata(text):
    if not text:
        return 1, 0, "Unknown", ""

    # Quality extraction
    qualities = ["2160p", "1440p", "1080p", "900p", "720p", "576p", "540p", "480p", "360p", "240p"]
    quality = "Unknown"
    for q in qualities:
        if q in text.lower():
            quality = q
            break

    # Season extraction
    season_match = re.search(r'(?:Season|S)\s*(\d+)', text, re.IGNORECASE)
    if not season_match:
        season_match = re.search(r'(\d+)x\d+', text, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else 1

    # Episode extraction
    episode_match = re.search(r'(?:Episode|EP|E)\s*(\d+)', text, re.IGNORECASE)
    if not episode_match:
        episode_match = re.search(r'\d+x(\d+)', text, re.IGNORECASE)
    if not episode_match:
        # Match - 01 or S01E01 part
        episode_match = re.search(r'(?:S\d+E|E|EP|Episode\s+|x)(\d+)', text, re.IGNORECASE)
    if not episode_match:
        # Fallback to any number that looks like an episode
        episode_match = re.search(r'(?:\s|-)(\d+)(?:\s|\.|$)', text)

    episode = int(episode_match.group(1)) if episode_match else 0

    # Title extraction
    clean_text = text
    # Remove file extension
    clean_text = re.sub(r'\.(?:mkv|mp4|avi|mp3|zip|rar)$', '', clean_text, flags=re.IGNORECASE)
    # Remove quality
    if quality != "Unknown":
        clean_text = re.sub(re.escape(quality), '', clean_text, flags=re.IGNORECASE)

    # Remove Season/Episode patterns
    clean_text = re.sub(r'(?:Season|S)\s*\d+', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'(?:Episode|EP|E)\s*\d+', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\d+x\d+', '', clean_text, flags=re.IGNORECASE)

    # Remove common tags
    clean_text = re.sub(r'\[.*?\]|\(.*?\)', '', clean_text)
    clean_text = re.sub(r'(?:x264|x265|10bit|WEB-DL|Multi Audio|ESub|Dual|DUB|Multi)', '', clean_text, flags=re.IGNORECASE)
    clean_text = clean_text.replace('-', ' ').replace('_', ' ').replace('.', ' ')

    title = ' '.join(clean_text.split()).strip()
    if not title:
        title = text.split('.')[0]

    return season, episode, quality, title

def get_metadata(caption, filename):
    # Process both
    s_c, e_c, q_c, t_c = extract_metadata(caption)
    s_f, e_f, q_f, t_f = extract_metadata(filename)

    # Metadata priority: Prefer caption for quality, but filename for structure usually
    s = s_c if s_c != 1 else s_f
    e = e_c if e_c != 0 else e_f
    q = q_c if q_c != "Unknown" else q_f
    t = t_f if t_f else t_c

    return s, e, q, t
