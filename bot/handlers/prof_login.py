import logging
from pyrogram import Client, filters, errors
from bot.config import Config
from bot.database.mongo import db

logger = logging.getLogger(__name__)

# Dictionary to store temporary clients during login
login_clients = {}

@Client.on_message(filters.command("login") & filters.user(Config.ADMINS) & filters.private, group=-2)
async def login_command(client, message):
    message.stop_propagation()
    user_id = message.from_user.id
    await db.reset_user(user_id)

    # Cleanup previous attempt if any
    if user_id in login_clients:
        try: await login_clients[user_id]["client"].disconnect()
        except: pass
        del login_clients[user_id]

    await db.update_user_state(user_id, "prof_login_awaiting_phone")
    await message.reply_text(
        "📱 **Professional Login**\n\n"
        "Please send your phone number in international format.\n"
        "Example: `+91XXXXXXXXXX`"
    )
    logger.info(f"Admin {user_id} started login flow.")

@Client.on_message(filters.private & filters.user(Config.ADMINS), group=-1)
async def handle_login_input(client, message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)
    if not state or not state.startswith("prof_login_"):
        return

    text = message.text.strip() if message.text else None
    if not text:
        return

    message.stop_propagation()

    if text == "/cancel":
        if user_id in login_clients:
            try: await login_clients[user_id]["client"].disconnect()
            except: pass
            del login_clients[user_id]
        await db.reset_user(user_id)
        logger.info(f"Admin {user_id} cancelled login.")
        return await message.reply_text("✅ Login cancelled.")

    if state == "prof_login_awaiting_phone":
        if not text.startswith("+"):
            return await message.reply_text("❌ Invalid format. Use: `+91XXXXXXXXXX`")

        temp_client = Client(
            f"login_{user_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            in_memory=True
        )

        try:
            await temp_client.connect()
            code = await temp_client.send_code(text)
            login_clients[user_id] = {
                "client": temp_client,
                "phone_number": text,
                "phone_code_hash": code.phone_code_hash
            }
            await db.update_user_state(user_id, "prof_login_awaiting_otp")
            await message.reply_text("📩 **OTP Sent!**\n\nPlease enter the code you received from Telegram.")
            logger.info(f"OTP sent to {text} for admin {user_id}.")
        except errors.FloodWait as e:
            await temp_client.disconnect()
            logger.warning(f"FloodWait during login for {user_id}: {e.value}s")
            return await message.reply_text(f"❌ FloodWait: Please wait {e.value} seconds.")
        except Exception as e:
            try: await temp_client.disconnect()
            except: pass
            logger.error(f"Login Step 1 Error for {user_id}: {e}")
            return await message.reply_text(f"❌ Error: {e}")

    elif state == "prof_login_awaiting_otp":
        if user_id not in login_clients:
            await db.update_user_state(user_id, None)
            return await message.reply_text("❌ Session expired. Please start again with /login")

        data = login_clients[user_id]
        temp_client = data["client"]

        try:
            # Handle various OTP formats (e.g. 1 2 3 4 5)
            otp = text.replace(" ", "")
            await temp_client.sign_in(data["phone_number"], data["phone_code_hash"], otp)

            # Success!
            session_string = await temp_client.export_session_string()
            await db.set_admin_session(session_string)
            await db.update_user_state(user_id, None)

            me = await temp_client.get_me()
            await message.reply_text(f"✅ **Login Successful!**\nConnected as: `{me.first_name}` (@{me.username or 'No Username'})")
            logger.info(f"Admin {user_id} logged in successfully as @{me.username}.")

            # Initialize the admin userbot in the main bot instance
            if hasattr(client, "init_admin_userbot"):
                await client.init_admin_userbot()

            await temp_client.disconnect()
            del login_clients[user_id]

        except errors.SessionPasswordNeeded:
            await db.update_user_state(user_id, "prof_login_awaiting_2fa")
            await message.reply_text("🔑 **Two-Step Verification Enabled**\n\nPlease enter your password.")
            logger.info(f"2FA required for admin {user_id}.")
        except errors.PhoneCodeInvalid:
            await message.reply_text("❌ Invalid code. Please try again.")
        except errors.PhoneCodeExpired:
            await temp_client.disconnect()
            del login_clients[user_id]
            await db.update_user_state(user_id, None)
            await message.reply_text("❌ Code expired. Please start again with /login")
        except Exception as e:
            logger.error(f"OTP Error for {user_id}: {e}")
            await message.reply_text(f"❌ Error: {e}")

    elif state == "prof_login_awaiting_2fa":
        if user_id not in login_clients:
            await db.update_user_state(user_id, None)
            return await message.reply_text("❌ Session expired. Please start again with /login")

        data = login_clients[user_id]
        temp_client = data["client"]

        try:
            await temp_client.check_password(text)

            # Success!
            session_string = await temp_client.export_session_string()
            await db.set_admin_session(session_string)
            await db.update_user_state(user_id, None)

            me = await temp_client.get_me()
            await message.reply_text(f"✅ **Login Successful (2FA)!**\nConnected as: `{me.first_name}` (@{me.username or 'No Username'})")
            logger.info(f"Admin {user_id} logged in successfully with 2FA as @{me.username}.")

            if hasattr(client, "init_admin_userbot"):
                await client.init_admin_userbot()

            await temp_client.disconnect()
            del login_clients[user_id]

        except errors.PasswordHashInvalid:
            await message.reply_text("❌ Wrong password. Please try again.")
        except Exception as e:
            logger.error(f"2FA Error for {user_id}: {e}")
            await message.reply_text(f"❌ Error: {e}")
