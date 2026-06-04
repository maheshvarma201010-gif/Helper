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

def sort_files(files):
    """
    Sorts files based on Season -> Episode -> Quality.
    This order better maintains the sequential viewing experience.
    """
    # Defensive programming: ensure all keys exist and are in correct format
    for f in files:
        if 'season' not in f or f['season'] is None: f['season'] = 1
        if 'episode' not in f or f['episode'] is None: f['episode'] = 0
        if 'quality' not in f or f['quality'] is None: f['quality'] = "Unknown"

    return sorted(
        files,
        key=lambda x: (
            int(x['season']),
            int(x['episode']),
            QUALITY_ORDER.get(x['quality'], 11)
        )
    )
