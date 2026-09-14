import os
import sys
import logging
import asyncio
import uvicorn

from app.config import Config
from app.database import Database
from app.bot import create_bot
from app.web import app as fastapi_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

async def main():
    missing_vars = Config.validate()
    if missing_vars:
        logger.warning(f"Missing configuration variables: {', '.join(missing_vars)}")

    # Connect to MongoDB
    await Database.connect()

    # Get runtime PORT internally from environment
    port = int(os.getenv("PORT", "8080"))

    # Web server config
    config = uvicorn.Config(
        app=fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)

    # Pyrogram bot instance
    bot = create_bot()

    logger.info(f"Starting Web Server on 0.0.0.0:{port} and Telegram Bot Client...")

    try:
        await bot.start()
        logger.info("Telegram Bot Client started successfully.")
        await server.serve()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
    finally:
        try:
            await bot.stop()
        except Exception:
            pass
        await Database.close()

if __name__ == "__main__":
    asyncio.run(main())
