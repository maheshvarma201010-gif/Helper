import logging
import asyncio
import os
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

async def health_check(request):
    return web.Response(text="Bot is running!")

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
        await super().start()
        me = await self.get_me()
        logger.info(f"Bot started as @{me.username}")

        # Ensure directories exist
        static_path = "bot/web/static"
        template_path = "bot/web/templates"
        os.makedirs(static_path, exist_ok=True)
        os.makedirs(template_path, exist_ok=True)

        # Peer caching logic
        await self.cache_peers()

        # Recover TEdit Tasks
        asyncio.create_task(self.recover_tedit_tasks())

        # Start Health Check & Redirect Server
        app = web.Application()
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_path))

        app.router.add_get("/", home_handler)
        app.router.add_get("/web-search", web_search_handler)
        app.router.add_get("/health", health_check)
        app.router.add_get("/go", redirect_handler)
        app.router.add_static("/static", static_path)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
        await site.start()
        logger.info(f"Health check server started on port {Config.PORT}")

    async def cache_peers(self):
        """
        Caches essential peers in the local storage to avoid 'Peer ID invalid' errors.
        """
        logger.info("Caching essential peers...")

        # Get channels from config and database
        channels_to_cache = set(Config.REPLACE_TEXT_CHANNELS)
        source_channel = await db.get_source_channel()
        if source_channel:
            channels_to_cache.add(source_channel)

        for chat_id in channels_to_cache:
            # Cache for Bot
            try:
                await self.get_chat(chat_id)
                logger.info(f"Cached chat {chat_id} for Bot")
            except Exception as e:
                logger.warning(f"Bot could not cache chat {chat_id}: {e}")

    async def recover_tedit_tasks(self):
        """
        Resumes any unfinished TEdit range tasks found in the database.
        """
        logger.info("Checking for unfinished TEdit tasks...")
        active_tasks = await db.get_active_tedit_tasks()

        for task in active_tasks:
            if task["type"] == "range":
                user_id = task["user_id"]
                logger.info(f"Resuming TEdit range task for user {user_id}")
                # We need a message object or status_msg_id to update progress
                # Since we can't easily re-fetch the original status message without its ID
                # We'll just start the background processing.
                # Note: This implementation assumes process_range_task handles its own status updates
                # if a status_msg is provided. We might want to save status_msg_id in the task.
                try:
                    # Minimal mock for status_msg if needed, or just let it run
                    # For now, we'll try to find if we have a status_msg_id
                    status_msg = None
                    # if "status_msg_id" in task:
                    #    status_msg = await self.get_messages(user_id, task["status_msg_id"])

                    from bot.handlers.tedit import process_range_task
                    asyncio.create_task(process_range_task(self, status_msg, user_id))
                except Exception as e:
                    logger.error(f"Failed to resume task for {user_id}: {e}")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    bot = Bot()
    bot.run()
