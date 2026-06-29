import asyncio
from typing import Dict
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from bot.config import Config
from bot.database.users import set_user_state, get_user_state
from bot.core.client import client_manager
from bot.core.peer_resolver import PeerResolver
from bot.core.validators import Validators
from bot.core.forward_engine import ForwardEngine
from bot.utils.keyboards import get_filter_keyboard
from bot.utils.constants import MessageTypes

# Global dictionary to track active engines
active_engines: Dict[int, ForwardEngine] = {}

@Client.on_message(filters.command("forward") & filters.private)
async def forward_command_handler(client: Client, message: Message):
    if message.from_user.id not in Config.ADMINS:
        return

    user_id = message.from_user.id
    user_client = await client_manager.get_user_client(user_id)
    if not user_client:
        return await message.reply("❌ You are not logged in. Use /login first.")

    await set_user_state(user_id, "awaiting_first_link")
    await message.reply("🔗 Please send the **First Message Link**.")

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help", "login", "logout", "forward", "forwardstop", "stats", "ping"]), group=2)
async def forward_state_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state_info = await get_user_state(user_id)
    if not state_info:
        return

    state = state_info.get("state")
    if not state or state not in ["awaiting_first_link", "awaiting_last_link", "awaiting_target"]:
        message.continue_propagation()
        return
    data = state_info.get("data", {})

    if state == "awaiting_first_link":
        if not Validators.is_valid_message_link(message.text):
            return await message.reply("❌ Invalid link. Please send a valid message link.")

        data["first_link"] = message.text
        await set_user_state(user_id, "awaiting_last_link", data)
        await message.reply("🔗 Now send the **Last Message Link**.")

    elif state == "awaiting_last_link":
        if not Validators.is_valid_message_link(message.text):
            return await message.reply("❌ Invalid link. Please send a valid message link.")

        data["last_link"] = message.text
        await set_user_state(user_id, "awaiting_target", data)
        await message.reply("🎯 Now send the **Target Channel** (Username, ID, or Link).\n\n💡 **Tip:** You can also **forward any message** from the target channel here to help the bot resolve it!")

    elif state == "awaiting_target":
        user_client = await client_manager.get_user_client(user_id)

        # FIX: Handle forwarded message to resolve PEER_ID_INVALID
        if message.forward_from_chat:
            target = message.forward_from_chat.id
        else:
            target = message.text.strip()

        try:
            # Simple check if target is accessible
            resolved_target = await PeerResolver.resolve(user_client, target)
            data["target"] = resolved_target.id

            # Also verify if bot is admin there (optional but good)
            if not await Validators.verify_permissions(client, resolved_target.id, is_bot=True):
                return await message.reply("❌ Bot needs to be an administrator in the target channel.")

            data["selected_filters"] = []
            await set_user_state(user_id, "selecting_filters", data)
            await message.reply(
                "📂 **Select message types to forward:**",
                reply_markup=get_filter_keyboard([])
            )
        except Exception as e:
            await message.reply(f"❌ Error: {e}")

    elif state == "awaiting_verification_forward":
        if not message.forward_from_chat:
            return await message.reply("❌ Please **forward** a message from the target channel.")

        target_id = message.forward_from_chat.id
        if target_id != data.get("target"):
             # If they send a different channel, we could update it or warn them.
             # For now, let's just update it to be safe.
             data["target"] = target_id

        await message.reply("✅ Target verified! Starting forwarding job...")
        asyncio.create_task(run_forward_job(client, user_id, data))
        await set_user_state(user_id, None)

@Client.on_callback_query(filters.regex(r"^(toggle_|select_all|clear_all|start_forward)"))
async def filter_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state_info = await get_user_state(user_id)

    if not state_info or state_info.get("state") != "selecting_filters":
        return await callback_query.answer("Session expired.", show_alert=True)

    data = state_info.get("data", {})
    selected = data.get("selected_filters", [])
    action = callback_query.data

    if action.startswith("toggle_"):
        filter_type = action.replace("toggle_", "")
        if filter_type in selected:
            selected.remove(filter_type)
        else:
            selected.append(filter_type)

    elif action == "select_all":
        selected = MessageTypes.ALL_TYPES.copy()

    elif action == "clear_all":
        selected = []

    elif action == "start_forward":
        if not selected:
            return await callback_query.answer("Please select at least one filter!", show_alert=True)

        # User requested: "bot ask forward msg ... after ask types"
        # This helps resolve PEER_ID_INVALID and confirms access
        await set_user_state(user_id, "awaiting_verification_forward", data)
        await callback_query.message.edit_text(
            "🛡️ **Final Verification Step**\n\n"
            "Please **forward any message** from the **Target Channel** to me here.\n"
            "This ensures I can resolve the channel ID correctly and have the necessary permissions."
        )
        return

    data["selected_filters"] = selected
    await set_user_state(user_id, "selecting_filters", data)

    try:
        await callback_query.message.edit_reply_markup(
            reply_markup=get_filter_keyboard(selected)
        )
    except:
        pass # Ignore if markup is same
    await callback_query.answer()

async def run_forward_job(bot_client: Client, user_id: int, data: Dict):
    user_client = await client_manager.get_user_client(user_id)

    first_id = PeerResolver.extract_message_id(data["first_link"])
    last_id = PeerResolver.extract_message_id(data["last_link"])
    source_chat = PeerResolver.extract_chat_id(data["first_link"])
    target_chat = data["target"]
    filters = data["selected_filters"]

    # Ensure range is correct
    start_id = min(first_id, last_id)
    end_id = max(first_id, last_id)

    status_msg = await bot_client.send_message(user_id, "🚀 Starting forwarding job...")

    engine = ForwardEngine(user_client, bot_client)
    active_engines[user_id] = engine

    try:
        await engine.start_forward(
            source_chat, target_chat, start_id, end_id, filters, status_msg
        )
    finally:
        if user_id in active_engines:
            del active_engines[user_id]
