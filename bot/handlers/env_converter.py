import io
import logging
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.security import auth_filter
from bot.utils.env_converter_util import convert_to_env

logger = logging.getLogger(__name__)

ENV_CONVERTER_SESSIONS: Dict[int, Dict[str, Any]] = {}

@Client.on_message(filters.command("env_converter") & auth_filter)
async def env_converter_command(client: Client, message: Message):
    user_id = message.from_user.id
    ENV_CONVERTER_SESSIONS[user_id] = {"step": "AWAIT_INPUT"}

    await message.reply_text(
        "📥 <b>Environment File Converter (/env_converter)</b>\n\n"
        "Please send your configuration file (e.g., <code>config.py</code>, <code>settings.py</code>, "
        "<code>.env</code>, <code>config.json</code>, <code>config.yaml</code>, or credential file) as a document attachment, "
        "or paste the raw config text directly in a message below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_env_converter")]
        ])
    )

@Client.on_callback_query(filters.regex("^cancel_env_converter$") & auth_filter)
async def cancel_env_converter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    ENV_CONVERTER_SESSIONS.pop(user_id, None)
    await callback_query.message.edit_text("❌ Environment file conversion canceled.")

@Client.on_message(filters.document & auth_filter, group=3)
async def env_converter_document_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = ENV_CONVERTER_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_INPUT":
        message.continue_propagation()
        return

    doc = message.document
    if not doc:
        await message.reply_text("❌ Invalid document received.")
        return

    msg = await message.reply_text("⏳ Processing and converting file to environment variables...")
    try:
        file_bytes = await client.download_media(doc, in_memory=True)
        if isinstance(file_bytes, io.BytesIO):
            content = file_bytes.getvalue().decode("utf-8", errors="ignore")
        elif isinstance(file_bytes, str):
            with open(file_bytes, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        else:
            content = ""

        converted = convert_to_env(content)
        if not converted:
            await msg.edit_text("❌ Could not extract any valid <code>KEY=value</code> environment variables from the file.")
            return

        ENV_CONVERTER_SESSIONS.pop(user_id, None)

        task_num = message.id
        filename = f"env_{user_id}_{task_num}.py"

        if len(converted) < 3500:
            await msg.edit_text(
                f"✅ <b>Converted Environment Variables (Saved as <code>{filename}</code>):</b>\n\n<code>{converted}</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Manage Render Env Vars", callback_data="manage_env")]
                ])
            )
            bio = io.BytesIO(converted.encode("utf-8"))
            bio.name = filename
            await message.reply_document(document=bio, caption=f"✅ Converted file: <code>{filename}</code>")
        else:
            await msg.edit_text(f"✅ <b>Converted Environment Variables:</b> (Sending <code>{filename}</code>...)")
            bio = io.BytesIO(converted.encode("utf-8"))
            bio.name = filename
            await message.reply_document(document=bio, caption=f"✅ Converted file: <code>{filename}</code>")

    except Exception as e:
        logger.error(f"Error converting document in /env_converter: {e}")
        await msg.edit_text(f"❌ Error processing file: {str(e)}")

@Client.on_message(filters.text & ~filters.command(["start", "help", "deploy", "create_repo", "zip", "repos", "projects", "status", "logs", "restart", "redeploy", "stop", "delete", "env", "env_converter", "settings"]) & auth_filter, group=3)
async def env_converter_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = ENV_CONVERTER_SESSIONS.get(user_id)
    if not session or session.get("step") != "AWAIT_INPUT":
        message.continue_propagation()
        return

    text = message.text.strip()
    converted = convert_to_env(text)

    if not converted:
        await message.reply_text("❌ Could not extract any valid <code>KEY=value</code> environment variables from the text.")
        return

    ENV_CONVERTER_SESSIONS.pop(user_id, None)

    task_num = message.id
    filename = f"env_{user_id}_{task_num}.py"

    if len(converted) < 3500:
        await message.reply_text(
            f"✅ <b>Converted Environment Variables (Saved as <code>{filename}</code>):</b>\n\n<code>{converted}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Manage Render Env Vars", callback_data="manage_env")]
            ])
        )
        bio = io.BytesIO(converted.encode("utf-8"))
        bio.name = filename
        await message.reply_document(document=bio, caption=f"✅ Converted file: <code>{filename}</code>")
    else:
        bio = io.BytesIO(converted.encode("utf-8"))
        bio.name = filename
        await message.reply_document(document=bio, caption=f"✅ Converted file: <code>{filename}</code>")
