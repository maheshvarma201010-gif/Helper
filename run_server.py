import asyncio
from aiohttp import web
from bot.web.server import create_web_app

async def main():
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Server running on port 8080")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
