import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from bot.database.mongo import db
from bot.utils.replacer import render_message_to_html
from bot.utils.hyperlink import parse_format_input, insert_hyperlinks

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("inserthy") & filters.private)
async def inserthy_command(client: Client, message: Message):
    user_id = message.from_user.id
    await db.reset_user(user_id)
    await db.update_user_state(user_id, "awaiting_inserthy_caption")
    await message.reply_text("📥 Please send the caption (or media with caption) where you want to insert hyperlinks.")

@Client.on_message(
    filters.private & (filters.text | filters.photo | filters.video | filters.document | filters.animation | filters.audio) & ~filters.command([
        "start", "sequence", "replace", "sort", "search", "cancel", "setchannel", "setbot", "reindex",
        "verify", "font", "fontchannel", "replace_domain", "b", "tedit", "tedit_status", "tedit_stop",
        "tedit_pause", "tedit_resume", "tedit_settings", "tedit_preview", "inserthy"
    ]),
    group=6
)
async def handle_inserthy_workflow(client: Client, message: Message):
    user_id = message.from_user.id
    state = await db.get_user_state(user_id)

    if not state or not state.startswith("awaiting_inserthy_"):
        message.continue_propagation()
        return

    if state == "awaiting_inserthy_caption":
        caption_html = ""
        if message.text:
            caption_html = render_message_to_html(message.text, message.entities)
        elif message.caption:
            caption_html = render_message_to_html(message.caption, message.caption_entities)

        if not caption_html:
            return await message.reply_text("❌ No text or caption found in your message. Please send a valid caption.")

        await db.users.update_one({"user_id": user_id}, {"$set": {"temp_inserthy_caption": caption_html}})
        await db.update_user_state(user_id, "awaiting_inserthy_format")

        prompt = (
            "🔗 Now, please send the hyperlink format.\n\n"
            "Example:\n"
            "`Multi Audio : https://example.com/multi1`\n"
            "`Multi Audio : https://example.com/multi2`\n"
            "`Telugu : https://example.com/telugu1`"
        )
        await message.reply_text(prompt)

    elif state == "awaiting_inserthy_format":
        user_doc = await db.users.find_one({"user_id": user_id})
        caption_html = user_doc.get("temp_inserthy_caption", "") if user_doc else ""

        if not caption_html:
            await db.update_user_state(user_id, None)
            return await message.reply_text("❌ Session expired or caption lost. Please start over with /inserthy.")

        format_text = message.text if message.text else ""
        mappings = parse_format_input(format_text)

        if not mappings:
            return await message.reply_text(
                "❌ Could not parse any format mappings. Please send the formats in the following structure:\n"
                "`Multi Audio : link`\n"
                "`Telugu : link`"
            )

        updated_caption, extra_links, missing_links = insert_hyperlinks(caption_html, mappings)

        # Build report notes if extra or missing links are present
        report_lines = []
        if extra_links:
            report_lines.append("⚠️ **Extra links provided (not enough matching text in caption):**")
            for target, unused in extra_links:
                for link in unused:
                    report_lines.append(f"• `{target}` : {link}")
            report_lines.append("")

        if missing_links:
            report_lines.append("⚠️ **Missing links (more occurrences in caption than links provided):**")
            for target, total_occs, provided_count in missing_links:
                report_lines.append(f"• `{target}` : needed {total_occs}, but only {provided_count} link(s) provided")
            report_lines.append("")

        # Clear temp data and state
        await db.users.update_one({"user_id": user_id}, {"$unset": {"temp_inserthy_caption": ""}})
        await db.update_user_state(user_id, None)

        if report_lines:
            report_msg = "\n".join(report_lines)
            await message.reply_text(report_msg)

        try:
            await message.reply_text(
                updated_caption,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error sending updated caption for inserthy: {e}")
            await message.reply_text(f"❌ Error sending updated caption: {e}\n\nProcessed HTML:\n`{updated_caption}`")
