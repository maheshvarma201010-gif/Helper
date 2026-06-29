import asyncio
from pyrogram import Client, filters, errors
from pyrogram.types import Message
from bot.config import Config
from bot.database.users import set_user_state, get_user_state
from bot.database.sessions import save_session
from bot.core.client import client_manager
from bot.core.logger import logger

@Client.on_message(filters.command("login") & filters.private)
async def login_handler(client: Client, message: Message):
    if message.from_user.id not in Config.ADMINS:
        return await message.reply("Unauthorized.")

    await set_user_state(message.from_user.id, "awaiting_phone")
    await message.reply("📱 Please enter your phone number with country code.\nExample: `+91XXXXXXXXXX`")

@Client.on_message(filters.private & ~filters.command(["start", "help", "login", "logout", "forward", "forwardstop", "stats", "ping"]), group=1)
async def auth_state_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state_info = await get_user_state(user_id)
    if not state_info:
        return

    state = state_info.get("state")
    if not state or not state.startswith("awaiting_"):
        message.continue_propagation()
        return

    if state not in ["awaiting_phone", "awaiting_otp", "awaiting_2fa"]:
        message.continue_propagation()
        return
    data = state_info.get("data", {})

    if state == "awaiting_phone":
        phone_number = message.text.strip().replace(" ", "")
        logger.info(f"Connecting temp client for {user_id} with phone {phone_number}")

        temp_client = Client(
            f"temp_{user_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            in_memory=True
        )
        await temp_client.connect()

        try:
            code_info = await temp_client.send_code(phone_number)
            data["phone"] = phone_number
            data["phone_code_hash"] = code_info.phone_code_hash
            # We store the temp client in client_manager temporarily
            client_manager.user_clients[f"temp_{user_id}"] = temp_client

            await set_user_state(user_id, "awaiting_otp", data)
            await message.reply("📨 OTP sent. Please enter the OTP in the format: `1 2 3 4 5` (with spaces) or `12345`.")
        except errors.FloodWait as e:
            await message.reply(f"❌ FloodWait: Please wait {e.value} seconds before trying again.")
            await temp_client.disconnect()
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            await message.reply(f"❌ Error: {e}")
            await temp_client.disconnect()

    elif state == "awaiting_otp":
        otp = message.text.strip().replace(" ", "")
        temp_client = client_manager.user_clients.get(f"temp_{user_id}")
        if not temp_client:
            await message.reply("Session expired. Please /login again.")
            return

        try:
            await temp_client.sign_in(data["phone"], data["phone_code_hash"], otp)
            await finalize_login(user_id, temp_client, message)
        except errors.SessionPasswordNeeded:
            await set_user_state(user_id, "awaiting_2fa", data)
            await message.reply("🔐 2FA password required. Please enter it.")
        except Exception as e:
            await message.reply(f"Error: {e}")

    elif state == "awaiting_2fa":
        password = message.text.strip()
        temp_client = client_manager.user_clients.get(f"temp_{user_id}")
        if not temp_client:
            await message.reply("Session expired. Please /login again.")
            return

        try:
            await temp_client.check_password(password)
            await finalize_login(user_id, temp_client, message)
        except Exception as e:
            await message.reply(f"Error: {e}")

async def finalize_login(user_id, temp_client, message):
    session_string = await temp_client.export_session_string()
    await save_session(user_id, session_string)

    # Move from temp to active
    await temp_client.stop()
    del client_manager.user_clients[f"temp_{user_id}"]

    # Re-initialize properly
    await client_manager.get_user_client(user_id)

    await set_user_state(user_id, None)
    await message.reply("✅ Logged in successfully!")
    logger.info(f"User {user_id} logged in.")
