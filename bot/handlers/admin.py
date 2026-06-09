import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.mongo import db
from bot.config import Config

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("stats") & filters.user(Config.ADMINS))
async def stats_command(client, message):
    sessions_count = await db.sessions.count_documents({})
    active_jobs = await db.get_all_active_forward_jobs()
    traces = await db.get_all_traces()

    text = (
        "📊 **Bot Statistics**\n\n"
        f"• **Stored Sessions:** `{sessions_count}`\n"
        f"• **Active Forward Jobs:** `{len(active_jobs)}`\n"
        f"• **Active Trace Tasks:** `{len(traces)}`\n"
    )

    buttons = [
        [InlineKeyboardButton("🔍 View Active Traces", callback_data="admin_view_traces")]
    ]

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^admin_view_traces"))
async def admin_view_traces(client, callback_query):
    traces = await db.get_all_traces()
    if not traces:
        return await callback_query.answer("No active traces found.", show_alert=True)

    text = "🔍 **Active Trace Tasks**\n\n"
    for i, trace in enumerate(traces, 1):
        text += f"{i}. From `{trace['source_chat']}` to `{trace['target_chat']}` (User: `{trace['user_id']}`)\n"

    buttons = []
    for trace in traces:
        buttons.append([InlineKeyboardButton(f"Stop {trace['source_chat']}", callback_data=f"stop_trace:{trace['user_id']}:{trace['source_chat']}")])

    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^stop_trace:(.+):(.+)"))
async def stop_trace_callback(client, callback_query):
    user_id = int(callback_query.matches[0].group(1))
    source_chat = callback_query.matches[0].group(2)

    await db.remove_trace(user_id, source_chat)
    await callback_query.answer(f"Stopped trace for {source_chat}")
    await admin_view_traces(client, callback_query)
