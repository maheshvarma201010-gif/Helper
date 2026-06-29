class MessageTypes:
    PHOTO = "🖼 Photos"
    DOCUMENT = "📄 Documents"
    VIDEO = "🎥 Videos"
    AUDIO = "🎵 Audio"
    VOICE = "🎤 Voice"
    ANIMATION = "🎬 GIFs"
    STICKER = "😀 Stickers"
    TEXT = "📝 Text"
    LINK = "🔗 Links"
    POLL = "📊 Polls"
    LOCATION = "📍 Locations"
    CONTACT = "👤 Contacts"
    ALBUM = "🎞 Albums"
    VIDEO_NOTE = "📹 Video Notes"

    ALL_TYPES = [
        PHOTO, DOCUMENT, VIDEO, AUDIO, VOICE, ANIMATION,
        STICKER, TEXT, LINK, POLL, LOCATION, CONTACT, ALBUM, VIDEO_NOTE
    ]

START_TEXT = "Welcome to the Production Forwarding Bot!"
HELP_TEXT = """
Available Commands:
/start - Start the bot
/help - Show this help message
/login - Login with your Telegram account
/logout - Logout from your account
/forward - Start a forwarding job
/forwardstop - Stop active forwarding job
/stats - View bot statistics
/ping - Check bot latency
"""
