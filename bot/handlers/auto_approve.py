import logging
from pyrogram import Client, filters, errors
from pyrogram.types import ChatJoinRequest
from bot.database.mongo import db
from bot.config import Config
from bot.utils.helpers import resolve_chat

logger = logging.getLogger(__name__)

@Client.on_chat_join_request()
async def auto_approve_handler(client, join_request: ChatJoinRequest):
    chat_id = join_request.chat.id
    user_id = join_request.from_user.id

    # Check if auto approve is enabled for this chat
    is_active = await db.get_auto_approve(chat_id)
    if not is_active:
        return

    try:
        await client.approve_chat_join_request(chat_id, user_id)
        logger.info(f"✅ Auto-approved {user_id} in {chat_id}")
    except errors.FloodWait as e:
        import asyncio
        await asyncio.sleep(e.value)
        await client.approve_chat_join_request(chat_id, user_id)
    except errors.UserAlreadyParticipant:
        pass
    except Exception as e:
        logger.error(f"❌ Failed to auto-approve {user_id} in {chat_id}: {e}")

@Client.on_message(filters.command("autoapprove") & filters.private)
async def auto_approve_cmd(client, message):
    # Check if user is admin
    if message.from_user.id not in Config.ADMINS and message.from_user.id != Config.OWNER_ID:
        return await message.reply_text("❌ This command is restricted to bot admins.")

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/autoapprove <chat_id> [on|off]`")

    args = message.command[1:]
    try:
        chat_id = int(args[0])
    except ValueError:
        return await message.reply_text("❌ Invalid Chat ID.")

    status = args[1].lower() if len(args) > 1 else None

    if status is None:
        current = await db.get_auto_approve(chat_id)
        return await message.reply_text(f"Auto-Approve for `{chat_id}` is currently: `{'ON' if current else 'OFF'}`")

    if status in ["on", "true", "yes", "1"]:
        try:
            chat = await resolve_chat(client, chat_id)
            # Verify bot permissions
            me = await chat.get_member(client.me.id)
            if not me.privileges or not me.privileges.can_invite_users:
                return await message.reply_text("❌ I need 'Invite Users' (Admin) permission to approve join requests.")

            await db.set_auto_approve(chat.id, True)
            await message.reply_text(f"✅ Auto-Approve enabled for `{chat.title}` ({chat.id})")
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
    elif status in ["off", "false", "no", "0"]:
        await db.set_auto_approve(chat_id, False)
        await message.reply_text(f"✅ Auto-Approve disabled for `{chat_id}`")
    else:
        await message.reply_text("Invalid status. Use `on` or `off`.")
