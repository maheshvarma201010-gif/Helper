import asyncio
from aiohttp import web
from bot.config import Config
from bot.core.client import client_manager
from bot.core.logger import logger

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()
    logger.info(f"Health check server started on port {Config.PORT}")

async def main():
    logger.info("Starting Forwarding Bot...")

    # Initialize bot client
    await client_manager.init_bot()

    # Load existing user sessions
    await client_manager.load_user_sessions()

    # Start web server for health checks
    await start_web_server()

    logger.info("Bot is now running. Press Ctrl+C to stop.")

    # Keep the bot running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
    finally:
        # Graceful shutdown
        if client_manager.bot_client:
            await client_manager.bot_client.stop()
        for user_id in list(client_manager.user_clients.keys()):
            await client_manager.stop_user_client(user_id)
        logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
