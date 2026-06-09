import logging
from pyrogram import Client, filters
from bot.database.mongo import db
from bot.config import Config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("ss") & filters.private)
async def ss_command(client, message):
    user_id = message.from_user.id
    await db.update_user_state(user_id, "awaiting_string_session")
    await message.reply_text(
        "👋 **String Session Setup**\n\n"
        "Please send your Pyrogram String Session.\n"
        "This session will be used for all forwarding operations.\n\n"
        "⚠️ **Security Note:** Your session is stored securely and only used for your forwarding tasks."
    )

@Client.on_message(filters.private & filters.text & filters.create(lambda _, __, m: not m.text.startswith("/")), group=6)
async def handle_session_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if state != "awaiting_string_session":
        message.continue_propagation()
        return

    string_session = message.text.strip()

    # Basic validation attempt
    try:
        temp_client = Client(
            "temp_session",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=string_session,
            in_memory=True
        )
        await temp_client.connect()
        me = await temp_client.get_me()
        await temp_client.disconnect()

        await db.set_session(user_id, string_session)
        await db.update_user_state(user_id, None)
        await message.reply_text(f"✅ **Session Saved Successfully!**\nConnected as: `{me.first_name}` (@{me.username or 'No Username'})")

    except Exception as e:
        logger.error(f"Session validation failed for {user_id}: {e}")
        await message.reply_text(f"❌ **Invalid String Session!**\nError: `{e}`\n\nPlease try again or send /cancel to abort.")
