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
    Each file in the list should be a dictionary containing:
    'season', 'episode', 'quality'
    """
    return sorted(
        files,
        key=lambda x: (
            x.get('season', 1),
            QUALITY_ORDER.get(x.get('quality', 'Unknown'), 11),
            x.get('episode', 0)
        )
    )
