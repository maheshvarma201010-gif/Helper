import json
from aiohttp import web
from bot.database.mongo import db

MINIAPP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Render Dashboard Mini App</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: #121824;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #4f46e5;
            --text-muted: #94a3b8;
            --border-color: #334155;
        }
        [data-theme="light"] {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-color: #0f172a;
            --accent-color: #4338ca;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
        }
        body {
            margin: 0;
            padding: 16px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            transition: background-color 0.3s, color 0.3s;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .title {
            font-size: 20px;
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-bottom: 16px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px;
            text-align: center;
        }
        .stat-num {
            font-size: 18px;
            font-weight: bold;
            margin-top: 4px;
        }
        .theme-toggle {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .service-name {
            font-size: 16px;
            font-weight: 600;
        }
        .badge {
            font-size: 12px;
            padding: 4px 8px;
            border-radius: 6px;
            background: #10b98122;
            color: #10b981;
            font-weight: 600;
        }
        .details {
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.5;
        }
        .btn-group {
            display: flex;
            gap: 8px;
            margin-top: 12px;
        }
        .btn {
            flex: 1;
            background: var(--accent-color);
            color: #ffffff;
            border: none;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">🚀 Render Dashboard</div>
        <button class="theme-toggle" onclick="toggleTheme()">🌓 Theme</button>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div style="font-size: 12px; color: var(--text-muted);">Total Services</div>
            <div class="stat-num" id="stat-total">1</div>
        </div>
        <div class="stat-card">
            <div style="font-size: 12px; color: var(--text-muted);">Running</div>
            <div class="stat-num" style="color: #10b981;" id="stat-running">1</div>
        </div>
        <div class="stat-card">
            <div style="font-size: 12px; color: var(--text-muted);">Stopped/Other</div>
            <div class="stat-num" style="color: #f59e0b;" id="stat-stopped">0</div>
        </div>
    </div>

    <div id="services-list">
        <div class="card">
            <div class="card-header">
                <span class="service-name">Render Deployer Bot</span>
                <span class="badge">🟢 RUNNING</span>
            </div>
            <div class="details">
                <div><b>Type:</b> Web Service (Docker)</div>
                <div><b>Repo:</b> github.com/owner/render-bot</div>
            </div>
            <div class="btn-group">
                <button class="btn" onclick="Telegram.WebApp.sendData('redeploy')">🚀 Redeploy</button>
                <button class="btn" onclick="Telegram.WebApp.sendData('restart')">🔁 Restart</button>
            </div>
        </div>
    </div>

    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        function toggleTheme() {
            const body = document.body;
            const current = body.getAttribute("data-theme");
            body.setAttribute("data-theme", current === "light" ? "dark" : "light");
        }
    </script>
</body>
</html>
"""

async def health_check_handler(request):
    try:
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

async def api_services_handler(request):
    user_id_str = request.query.get("user_id")
    if not user_id_str or not user_id_str.isdigit():
        return web.Response(
            text=json.dumps({"status": "error", "message": "Valid user_id parameter required"}),
            content_type="application/json",
            status=400
        )

    user_id = int(user_id_str)
    try:
        deployments = await db.get_user_deployments(user_id)
        services_data = []
        for d in deployments:
            services_data.append({
                "service_id": d.get("service_id"),
                "service_name": d.get("service_name"),
                "repo_url": d.get("repo_url"),
                "branch": d.get("branch", "main"),
                "service_type": d.get("service_type", "web_service"),
                "is_docker": d.get("is_docker", False),
                "status": d.get("status", "created"),
                "service_url": d.get("service_url")
            })

        total = len(services_data)
        running = sum(1 for s in services_data if s["status"] in ["live", "created", "running"])
        stopped = total - running

        return web.Response(
            text=json.dumps({
                "status": "success",
                "summary": {"total": total, "running": running, "stopped": stopped},
                "services": services_data
            }),
            content_type="application/json",
            status=200
        )
    except Exception as e:
        return web.Response(
            text=json.dumps({"status": "error", "message": str(e)}),
            content_type="application/json",
            status=500
        )

async def miniapp_handler(request):
    return web.Response(text=MINIAPP_HTML, content_type="text/html")

def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", health_check_handler)
    app.router.add_get("/miniapp", miniapp_handler)
    app.router.add_get("/api/services", api_services_handler)
    return app
