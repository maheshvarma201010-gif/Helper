import re
from bot.database.mongo import db

def parse_search_query(query):
    """
    Extracts title, season, and episode from a search query.
    Example: 'naruto s01 ep05' -> ('naruto', 1, 5)
    """
    season_match = re.search(r'(?:Season|S)\s*(\d+)', query, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else None

    episode_match = re.search(r'(?:Episode|EP|E)\s*(\d+)', query, re.IGNORECASE)
    episode = int(episode_match.group(1)) if episode_match else None

    # Remove metadata patterns from query to get the 'title' part
    clean_query = re.sub(r'(?:Season|S|Episode|EP|E)\s*\d+', '', query, flags=re.IGNORECASE).strip()

    return clean_query, season, episode

async def search_files(query):
    """
    Performs fuzzy search in the MongoDB index.
    """
    title, season, episode = parse_search_query(query)

    mongo_filter = {}
    if title:
        # Use regex for partial, case-insensitive match on title or filename
        regex = re.compile(re.escape(title), re.IGNORECASE)
        mongo_filter["$or"] = [
            {"title": {"$regex": regex}},
            {"filename": {"$regex": regex}}
        ]

    if season is not None:
        mongo_filter["season"] = season

    if episode is not None:
        mongo_filter["episode"] = episode

    results = await db.search_index(mongo_filter)

    # Group results by Quality
    # Expected qualities: 480p, 720p, 1080p, 2160p
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
