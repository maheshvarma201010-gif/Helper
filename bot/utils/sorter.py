QUALITY_ORDER = {
    "240p": 1,
    "360p": 2,
    "480p": 3,
    "540p": 4,
    "576p": 5,
    "720p": 6,
    "900p": 7,
    "1080p": 8,
    "1440p": 9,
    "2160p": 10,
    "Unknown": 11
}

def sort_files(files, sort_type="standard"):
    """
    Sorts files based on the requested sort_type.
    """
    # Defensive programming: ensure all keys exist and are in correct format
    for f in files:
        if 'season' not in f or f['season'] is None: f['season'] = 1
        if 'episode' not in f or f['episode'] is None: f['episode'] = 0
        if 'quality' not in f or f['quality'] is None: f['quality'] = "Unknown"
        if 'filename' not in f: f['filename'] = ""

    if sort_type == "standard": # Season -> Episode -> Quality
        key = lambda x: (int(x['season']), int(x['episode']), QUALITY_ORDER.get(x['quality'], 11))
    elif sort_type == "episode_wise": # Episode -> Season -> Quality
        key = lambda x: (int(x['episode']), int(x['season']), QUALITY_ORDER.get(x['quality'], 11))
    elif sort_type == "quality_wise": # Quality -> Season -> Episode
        key = lambda x: (QUALITY_ORDER.get(x['quality'], 11), int(x['season']), int(x['episode']))
    elif sort_type == "filename_wise": # Alphabetical Filename
        key = lambda x: x['filename'].lower()
    elif sort_type == "season_only": # Just Season
        key = lambda x: int(x['season'])
    elif sort_type == "episode_only": # Just Episode
        key = lambda x: int(x['episode'])
    elif sort_type == "reverse": # Reverse chronological (assuming timestamp was added)
        key = lambda x: -x.get('timestamp', 0)
    else:
        key = lambda x: (int(x['season']), int(x['episode']), QUALITY_ORDER.get(x['quality'], 11))

    return sorted(files, key=key)
