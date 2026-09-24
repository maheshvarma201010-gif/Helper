import logging
from typing import Dict, Any, List, Optional
from bot.utils.formatter import sanitize_service_name

logger = logging.getLogger(__name__)

def update_env_base_urls(env_vars: Dict[str, str], old_url: str = "", new_url: str = "") -> Dict[str, str]:
    """
    Automatically updates BASE_URL, CDN_URL, WEBSITE_URL, or any matching URL references
    in environment variables to the new service URL.
    """
    updated = dict(env_vars) if env_vars else {}

    if not new_url:
        return updated

    clean_old_url = old_url.rstrip("/") if old_url else ""
    clean_new_url = new_url.rstrip("/")

    # Update explicit BASE_URL if present or missing
    if "BASE_URL" in updated or not updated:
        updated["BASE_URL"] = clean_new_url

    # Replaces old_url occurrences across all env vars
    for k, v in list(updated.items()):
        if not isinstance(v, str):
            continue

        if k.upper() in ["BASE_URL", "WEBSITE_URL", "CDN_URL", "APP_URL", "URL"]:
            updated[k] = clean_new_url
        elif clean_old_url and clean_old_url in v:
            updated[k] = v.replace(clean_old_url, clean_new_url)

    return updated
