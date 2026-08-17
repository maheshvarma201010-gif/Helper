from typing import Optional, Tuple
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.utils.render_api import RenderAPI, RenderAPIError

GITHUB_AUTH_URL = "https://github.com/apps/render/installations/new"

async def check_user_github_connection(user_id: int) -> Tuple[bool, Optional[str], Optional[InlineKeyboardMarkup]]:
    """
    Checks if user has configured Render API key and if Render account is connected to GitHub.
    If not connected, returns (False, error_message, keyboard_with_auth_link).
    """
    api_key = await db.get_user_render_key(user_id)
    if not api_key:
        msg = (
            "🔑 <b>Render API Key Required</b>\n\n"
            "You have not configured your Render API Key yet.\n"
            "Please configure your Render API Key in /settings or send it using /settings."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
        ])
        return False, msg, kb

    # Validate Render API Key
    try:
        render_api = RenderAPI(api_key)
        owner_id = await render_api.get_owner_id()
        if not owner_id:
            msg = (
                "❌ <b>Invalid Render API Key</b>\n\n"
                "Could not authenticate with Render API. Please check your key in /settings."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Update API Key", callback_data="open_settings")]
            ])
            return False, msg, kb
    except RenderAPIError as e:
        msg = f"❌ <b>Render API Error:</b> {e.message}\nPlease update your API Key in /settings."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Settings", callback_data="open_settings")]
        ])
        return False, msg, kb
    except Exception as e:
        msg = f"❌ <b>Connection Error:</b> {str(e)}"
        return False, msg, None

    # Account is connected & authenticated
    return True, None, None

def get_github_connect_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Connect GitHub to Render", url=GITHUB_AUTH_URL)],
        [InlineKeyboardButton("🔄 Verify Connection", callback_data="verify_github_conn")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ])
