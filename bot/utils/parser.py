import re

def extract_metadata(text):
    if not text:
        return 1, 0, "Unknown"

    # Season extraction
    season_match = re.search(r'(?:Season|S)\s*(\d+)', text, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else 1

    # Episode extraction
    episode_match = re.search(r'(?:Episode|EP|E)\s*(\d+)', text, re.IGNORECASE)
    episode = int(episode_match.group(1)) if episode_match else 0

    # Quality extraction
    qualities = ["2160p", "1440p", "1080p", "900p", "720p", "576p", "540p", "480p", "360p", "240p"]
    quality = "Unknown"
    for q in qualities:
        if q in text:
            quality = q
            break

    return season, episode, quality

def get_metadata(caption, filename):
    # Priority 1: Caption
    s, e, q = extract_metadata(caption)

    # Check if we found anything useful in caption
    # If it's default (1, 0, "Unknown"), try filename
    if s == 1 and e == 0 and q == "Unknown":
        # Priority 2: Filename
        s_f, e_f, q_f = extract_metadata(filename)
        return s_f, e_f, q_f

    # If caption had some but not all, we might want to blend or just stick with priority
    # For now, let's stick to the rule: Priority 2 only if metadata missing from caption.
    # "Missing" is a bit ambiguous, but let's assume if we found NO episode and NO quality, it's missing.

    if e == 0 and q == "Unknown":
         s_f, e_f, q_f = extract_metadata(filename)
         if e_f != 0 or q_f != "Unknown":
             return s_f, e_f, q_f

    return s, e, q
