import re
from bot.database.mongo import db

def parse_search_query(query):
    """
    Extracts title, season, and episode from a search query.
    Example: 'naruto s01 ep05' -> ('naruto', 1, 5)
    """
    # Detect Season
    season_match = re.search(r'(?:Season|S)\s*(\d+)', query, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else None

    # Detect Episode
    episode_match = re.search(r'(?:Episode|EP|E)\s*(\d+)', query, re.IGNORECASE)
    episode = int(episode_match.group(1)) if episode_match else None

    # Clean query to extract the title part
    clean_query = query
    clean_query = re.sub(r'(?:Season|S)\s*\d+', '', clean_query, flags=re.IGNORECASE)
    clean_query = re.sub(r'(?:Episode|EP|E)\s*\d+', '', clean_query, flags=re.IGNORECASE)

    # Detect Quality in query
    qualities = ["2160p", "1440p", "1080p", "900p", "720p", "576p", "540p", "480p", "360p", "240p"]
    query_quality = None
    for q in qualities:
        if q in clean_query.lower():
            query_quality = q
            clean_query = clean_query.lower().replace(q, '')
            break

    title = ' '.join(clean_query.split()).strip()

    return title, season, episode, query_quality

async def search_files(query):
    """
    Performs fuzzy search in the MongoDB index.
    """
    title, season, episode, query_quality = parse_search_query(query)

    mongo_filter = {}
    if title:
        # Use a more flexible regex for title search
        # Split title into words and create a regex that matches them in any order or sequence
        words = title.split()
        if len(words) > 1:
            # Match all words
            regex_pattern = '.*'.join([re.escape(word) for word in words])
            regex = re.compile(regex_pattern, re.IGNORECASE)
        else:
            regex = re.compile(re.escape(title), re.IGNORECASE)

        mongo_filter["$or"] = [
            {"title": {"$regex": regex}},
            {"filename": {"$regex": regex}},
            {"caption": {"$regex": regex}}
        ]

    if season is not None:
        mongo_filter["season"] = season

    if episode is not None:
        mongo_filter["episode"] = episode

    if query_quality:
        mongo_filter["quality"] = query_quality

    results = await db.search_index(mongo_filter)

    # Group results by Quality
    grouped = {
        "480p": [],
        "720p": [],
        "1080p": [],
        "2160p": [],
        "Unknown": []
    }

    for item in results:
        q = item.get("quality", "Unknown")
        if q not in grouped:
            grouped["Unknown"].append(item)
        else:
            grouped[q].append(item)

    return grouped, title, season
