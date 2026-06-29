import asyncio
from bot.core.client import client_manager
from bot.core.logger import logger

async def main():
    logger.info("Starting Forwarding Bot...")

    # Initialize bot client
    await client_manager.init_bot()

    # Load existing user sessions
    await client_manager.load_user_sessions()

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
