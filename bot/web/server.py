import json
from aiohttp import web
from bot.database.mongo import db

async def health_check_handler(request):
    try:
        # Simple ping to db
        db.connect()
        return web.Response(
            text=json.dumps({"status": "healthy", "service": "Render Deployer Bot"}),
            content_type="application/json",
            status=200
        )
    except Exception as e:
        return web.Response(
            text=json.dumps({"status": "unhealthy", "error": str(e)}),
            content_type="application/json",
            status=500
        )

def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", health_check_handler)
    return app
