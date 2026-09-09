import logging
import asyncio
import os
import json
import aiohttp_jinja2
import jinja2
from pyrogram import Client, errors
from aiohttp import web
from bot.config import Config
from bot.database.mongo import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot_instance = None

async def health_check(request):
    active_jobs = await db.get_all_active_tedit_jobs()
    status = {
        "status": "running",
        "active_tedit_jobs": len(active_jobs),
        "jobs": [
            {
                "job_id": j["job_id"],
                "status": j["status"],
                "processed": j.get("total_processed", 0)
            } for j in active_jobs
        ]
    }
    return web.Response(text=json.dumps(status), content_type="application/json")

async def home_handler(request):
    page = int(request.query.get('page', 1))
    limit = 20
    skip = (page - 1) * limit

    items = await db.get_all_indexed(limit=limit, skip=skip)
    recent = await db.get_recent_posts(hours=24)

    # Simple total count for pagination
    total_count = await db.indexes.count_documents({})
    total_pages = (total_count + limit - 1) // limit

    context = {
        "items": items,
        "recent_posts": recent,
        "current_page": page,
        "total_pages": total_pages
    }
    return aiohttp_jinja2.render_template("index.html", request, context)

async def web_search_handler(request):
    query = request.query.get('q', '')
    if not query:
        return web.HTTPFound('/')

    # Reuse search logic from search_engine but simplified for web
    query_filter = {"$or": [
        {"title": {"$regex": query, "$options": "i"}},
        {"caption": {"$regex": query, "$options": "i"}},
        {"filename": {"$regex": query, "$options": "i"}}
    ]}
    items = await db.indexes.find(query_filter).sort("message_id", -1).to_list(length=100)
    recent = await db.get_recent_posts(hours=24)

    context = {
        "items": items,
        "recent_posts": recent,
        "query": query,
        "current_page": 1,
        "total_pages": 1
    }
    return aiohttp_jinja2.render_template("index.html", request, context)

async def ensure_local_media_file(file_data):
    """
    Ensures that the video file and its extracted audio tracks exist on disk.
    If missing (e.g. after server restart or container purge), re-downloads
    from FILE_CHANNEL or the original Telegram message on demand.
    """
    if not file_data:
        return None

    file_id = file_data["file_id"]
    file_path = file_data.get("file_path")
    file_dir = file_data.get("file_dir") or os.path.join("downloads", file_id)
    os.makedirs(file_dir, exist_ok=True)

    if not file_path:
        file_name = file_data.get("file_name", "video.mp4")
        file_path = os.path.join(file_dir, file_name)
        file_data["file_path"] = file_path

    # Check if file exists and has size
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_data

    # File missing on disk, fetch from Telegram
    if not bot_instance:
        logger.error("bot_instance is None, cannot re-download media on demand")
        return file_data

    target_chat = file_data.get("file_channel_id") or file_data.get("chat_id")
    target_msg_id = file_data.get("file_channel_message_id") or file_data.get("message_id")

    if not target_chat or not target_msg_id:
        logger.error(f"No valid chat/message ID for re-downloading file_id {file_id}")
        return file_data

    try:
        logger.info(f"On-demand fetching missing media {file_id} from chat {target_chat}, msg {target_msg_id}")
        target_msg = await bot_instance.get_messages(target_chat, target_msg_id)
        if target_msg and (target_msg.video or target_msg.document):
            await bot_instance.download_media(message=target_msg, file_name=file_path)

            from bot.utils.media import extract_audio_tracks
            tracks = await extract_audio_tracks(file_path, file_dir)
            file_data["audio_tracks"] = tracks
            file_data["file_path"] = file_path
            await db.add_media_file(file_data)
            logger.info(f"Successfully re-cached missing media {file_id} on demand!")
    except Exception as e:
        logger.exception(f"Failed on-demand download for file_id {file_id}: {e}")

    return file_data

async def watch_handler(request):
    file_id = request.match_info.get('file_id')
    file_data = await db.get_media_file(file_id)
    if not file_data:
        return web.Response(text="404 File Not Found", status=404)

    file_data = await ensure_local_media_file(file_data)

    recent = await db.get_recent_posts(hours=24)
    context = {
        "file": file_data,
        "recent_posts": recent
    }
    return aiohttp_jinja2.render_template("watch.html", request, context)

async def download_handler(request):
    file_id = request.match_info.get('file_id')
    file_data = await db.get_media_file(file_id)
    if not file_data:
        return web.Response(text="404 File Not Found", status=404)

    file_data = await ensure_local_media_file(file_data)
    file_path = file_data.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return web.Response(text="404 File Not Available on Server", status=404)

    filename = file_data.get("file_name", "download.mp4")
    ext = os.path.splitext(filename)[1].lower()

    content_type = file_data.get("mime_type")
    if not content_type or content_type == "application/octet-stream":
        if ext == ".mkv":
            content_type = "video/x-matroska"
        elif ext == ".mp4":
            content_type = "video/mp4"
        elif ext == ".webm":
            content_type = "video/webm"
        else:
            content_type = "video/mp4"

    return web.FileResponse(
        path=file_path,
        headers={
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

async def audio_track_handler(request):
    file_id = request.match_info.get('file_id')
    try:
        track_index = int(request.match_info.get('track_index', 0))
    except ValueError:
        return web.Response(text="Invalid track index", status=400)

    file_data = await db.get_media_file(file_id)
    if not file_data:
        return web.Response(text="404 File Not Found", status=404)

    file_data = await ensure_local_media_file(file_data)
    audio_tracks = file_data.get("audio_tracks", [])
    target_track = None
    for track in audio_tracks:
        if track.get("audio_index") == track_index:
            target_track = track
            break

    if not target_track:
        return web.Response(text="404 Audio Track Not Found", status=404)

    audio_path = target_track.get("file_path")
    if not audio_path or not os.path.exists(audio_path):
        return web.Response(text="404 Audio Track File Not Found", status=404)

    audio_filename = target_track.get("file_name", f"audio_track_{track_index}.aac")
    ext = os.path.splitext(audio_filename)[1].lower()

    if ext in [".aac", ".m4a"]:
        audio_content_type = "audio/aac"
    elif ext == ".mp3":
        audio_content_type = "audio/mpeg"
    elif ext == ".ogg":
        audio_content_type = "audio/ogg"
    else:
        audio_content_type = "audio/aac"

    return web.FileResponse(
        path=audio_path,
        headers={
            "Content-Type": audio_content_type,
            "Content-Disposition": f'inline; filename="{audio_filename}"'
        }
    )

async def redirect_handler(request):
    url = request.query.get('url')
    if not url:
        return web.Response(text="Missing URL parameter", status=400)

    # HTML with JavaScript and Meta Refresh redirect
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="0;url={url}">
        <title>Redirecting...</title>
        <script type="text/javascript">
            window.location.href = "{url}";
        </script>
    </head>
    <body>
        <p>If you are not redirected, <a href="{url}">click here</a>.</p>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

class Bot(Client):
    def __init__(self):
        super().__init__(
            "file_sequencer_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/handlers")
        )

    async def start(self):
        global bot_instance
        bot_instance = self
        await super().start()
        me = await self.get_me()
        logger.info(f"Bot started as @{me.username}")

        # Send test message to FILE_CHANNEL to verify credentials & access
        if Config.FILE_CHANNEL:
            try:
                await self.send_message(
                    Config.FILE_CHANNEL,
                    "🤖 **File Channel Connected!**\nFile storage & streaming system is active."
                )
                logger.info(f"Verified FILE_CHANNEL ({Config.FILE_CHANNEL}) successfully.")
            except Exception as e:
                logger.warning(f"Could not send test message to FILE_CHANNEL ({Config.FILE_CHANNEL}): {e}")

        from pyrogram.types import BotCommand
        await self.set_bot_commands([
            BotCommand("start", "Start the bot"),
            BotCommand("link", "Generate Watch & Download links for a video"),
            BotCommand("forward", "Cleanly copy messages between links"),
            BotCommand("ss", "Save your string session"),
            BotCommand("auto", "Configure default button templates"),
            BotCommand("inserthy", "Insert hyperlinks into caption text"),
            BotCommand("scrab", "Extract buttons from a post link"),
            BotCommand("tedit", "Watermarking menu"),
            BotCommand("stats", "Admin statistics"),
            BotCommand("cancel", "Cancel current setup/wizard"),
            BotCommand("stop", "Terminate active forwarding jobs")
        ])

        # Ensure directories exist
        static_path = "bot/web/static"
        template_path = "bot/web/templates"
        os.makedirs(static_path, exist_ok=True)
        os.makedirs(template_path, exist_ok=True)

        # Peer caching logic
        await self.cache_peers()

        # Start Health Check & Redirect Server
        app = web.Application()
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_path))

        app.router.add_get("/", home_handler)
        app.router.add_get("/web-search", web_search_handler)
        app.router.add_get("/health", health_check)
        app.router.add_get("/go", redirect_handler)
        app.router.add_get("/watch/{file_id}", watch_handler)
        app.router.add_get("/download/{file_id}", download_handler)
        app.router.add_get("/audio/{file_id}/{track_index}", audio_track_handler)
        app.router.add_static("/static", static_path)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
        await site.start()
        logger.info(f"Health check server started on port {Config.PORT}")

        # Start TEdit Worker
        from bot.handlers.tedit import init_worker
        await init_worker(self)

        # Start Forward Worker
        from bot.handlers.forward import init_forward_worker
        await init_forward_worker(self)

    async def cache_peers(self):
        """
        Caches essential peers in the local storage to avoid 'Peer ID invalid' errors.
        """
        logger.info("Caching essential peers...")

        # Get channels from config and database
        channels_to_cache = set(Config.REPLACE_TEXT_CHANNELS)
        if Config.LOG_CHANNEL:
            channels_to_cache.add(Config.LOG_CHANNEL)
        if Config.FILE_CHANNEL:
            channels_to_cache.add(Config.FILE_CHANNEL)
        source_channel = await db.get_source_channel()
        if source_channel:
            channels_to_cache.add(source_channel)

        for chat_id in channels_to_cache:
            # Cache for Bot
            try:
                # Ensure chat_id is properly formatted for get_chat
                target = chat_id
                if isinstance(target, str) and not target.startswith("@") and not target.lstrip("-").isdigit():
                    target = f"@{target}"

                await self.get_chat(target)
                logger.info(f"Cached chat {target} for Bot")
            except errors.PeerIdInvalid:
                logger.warning(f"Bot could not cache chat {chat_id}: Peer ID invalid (Bot might not have access)")
            except Exception as e:
                logger.warning(f"Bot could not cache chat {chat_id}: {e}")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    bot = Bot()
    bot.run()
