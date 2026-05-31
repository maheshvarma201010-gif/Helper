import re
from bot.database.mongo import db

def parse_search_query(query):
    """
    Extracts title, season, and episode from a search query.
    """
    # Detect Season
    season_match = re.search(r'(?:Season|S)\s*(\d+)', query, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else None

    # Detect Episode
    episode_match = re.search(r'(?:Episode|EP|E)\s*(\d+)', query, re.IGNORECASE)
    episode = int(episode_match.group(1)) if episode_match else None

    # Detect Quality
    qualities = ["2160p", "1440p", "1080p", "900p", "720p", "576p", "540p", "480p", "360p", "240p"]
    query_quality = None

    clean_query = query
    for q in qualities:
        if q in clean_query.lower():
            query_quality = q
            clean_query = re.sub(re.escape(q), '', clean_query, flags=re.IGNORECASE)
            break

    clean_query = re.sub(r'(?:Season|S|Episode|EP|E)\s*\d+', '', clean_query, flags=re.IGNORECASE)
    title = ' '.join(clean_query.split()).strip()

    return title, season, episode, query_quality

async def search_files(query):
    """
    Performs resilient search in the MongoDB index.
    """
    title, season, episode, query_quality = parse_search_query(query)

    mongo_filter = {}

    if title:
        # Split title into keywords for broad matching
        keywords = [re.escape(k) for k in title.split() if len(k) > 1]
        if keywords:
            # Match messages that contain ALL keywords in any order
            regex_pattern = "".join([f"(?=.*{k})" for k in keywords])
            regex = re.compile(regex_pattern, re.IGNORECASE)

            mongo_filter["$or"] = [
                {"title": {"$regex": regex}},
                {"filename": {"$regex": regex}},
                {"caption": {"$regex": regex}}
            ]
        else:
            # Fallback to simple regex if query is too short
            regex = re.compile(re.escape(title), re.IGNORECASE)
            mongo_filter["$or"] = [
                {"title": {"$regex": regex}},
                {"filename": {"$regex": regex}}
            ]

    if season is not None:
        mongo_filter["season"] = season

    if episode is not None:
        mongo_filter["episode"] = episode

    if query_quality:
        mongo_filter["quality"] = query_quality

    results = await db.search_index(mongo_filter)

    # Group results by Quality
    grouped = {"480p": [], "720p": [], "1080p": [], "2160p": [], "Unknown": []}

    for item in results:
        q = item.get("quality", "Unknown")
        if q in grouped:
            grouped[q].append(item)
        else:
            grouped["Unknown"].append(item)

    return grouped, title, season
