import logging
from pyrogram import utils

logger = logging.getLogger(__name__)

def apply_patches():
    """
    Applies necessary monkey-patches to Pyrogram to support newer Telegram features
    and resolve common issues.
    """

    # 1. Patch get_peer_type to support newer large Telegram IDs
    # Without this, Pyrogram raises ValueError: Peer id invalid for IDs like -1002...
    original_get_peer_type = utils.get_peer_type

    def get_peer_type_patched(peer_id: int) -> str:
        if peer_id > 0:
            return "user"

        # Newer large IDs can exceed the standard bitwise checks
        # So we use a simpler but more robust check
        peer_id_str = str(peer_id)
        if peer_id_str.startswith("-100"):
            return "channel"
        if peer_id_str.startswith("-"):
            return "chat"

        return "user"

    utils.get_peer_type = get_peer_type_patched
    logger.info("Applied robust Pyrogram Peer ID monkey-patch.")

    # Future patches can be added here
