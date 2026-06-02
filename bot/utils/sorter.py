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
    Sorts files based on Season -> Quality -> Episode.
    """
    # Defensive programming: ensure all keys exist
    for f in files:
        if 'season' not in f: f['season'] = 1
        if 'episode' not in f: f['episode'] = 0
        if 'quality' not in f: f['quality'] = "Unknown"

    return sorted(
        files,
        key=lambda x: (
            int(x['season']),
            QUALITY_ORDER.get(x['quality'], 11),
            int(x['episode'])
        )
    )
