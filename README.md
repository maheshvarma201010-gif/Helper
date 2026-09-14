# Telegram Docker Deploy Manager 🐳

A complete, production-ready Telegram Bot and HTTP web server for managing and deploying Docker projects directly via Telegram commands.

---

## 🌟 Features

- **Project Creation & Deployment**: Upload a repository `.zip` file containing a `Dockerfile` to build and deploy Docker containers.
- **Dockerfile Auto-Detection**: Supports both root `/Dockerfile` and single-level directory `/project-name/Dockerfile`.
- **Zero-Downtime Safe Replacement**: Replace an existing project's ZIP archive without downtime. Safe rollbacks ensure working deployments are never destroyed if a new build fails.
- **Environment (.env) Configuration**: Upload or update `.env` variables for any project safely without exposing secrets in Telegram or Docker images.
- **Project Controls**: Start, pause, stop, restart, redeploy, or remove projects using inline Telegram keyboards or slash commands.
- **Live Logs & Error Handling**: Stream container logs directly in Telegram messages or receive log text files for larger outputs.
- **Strict Authorization**: Multi-admin access control restricted to `OWNER_ID` and `ADMIN_IDS`.
- **Render Ready**: Built-in FastAPI health server (`GET /` and `GET /health`) bound to `0.0.0.0` and runtime `PORT`.
- **MongoDB Persistence**: Uses Motor for asynchronous persistence of project state and environment configurations.
- **Secure Extraction**: Full protection against path traversal (`..`), absolute path injection, malicious symlinks, and ZIP bombs.

---

## ⚠️ Important Hosting Note: Render & Docker Engine Requirements

When deploying this application on **Render**:
- The bot itself and its HTTP server run smoothly on Render Web Services.
- **Docker Engine Limitation**: Standard Render Web Services run inside unprivileged containers without access to a Docker daemon or Docker socket (`/var/run/docker.sock`).
- If Docker Engine is unavailable in the environment, deployment commands will notify the admin:
  `❌ Docker Engine is not available in the current hosting environment.`
- The bot remains fully functional and online on Render. To execute arbitrary Docker deployments (`/deploy`), run this manager on a Linux VPS or server where Docker Engine and socket access are available (or mount `/var/run/docker.sock`).

---

## ⚙️ Environment Variables

The configuration strictly requires **ONLY** the following 7 environment variables:

| Variable | Description |
|---|---|
| `API_ID` | Telegram API ID (integer) from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | Telegram API Hash string |
| `BOT_TOKEN` | Telegram Bot Token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Comma-separated list of authorized admin Telegram user IDs |
| `OWNER_ID` | Telegram user ID of the primary owner (full privileges) |
| `BASE_URL` | Base public URL for web server / webhooks |
| `MONGODB_URL` | MongoDB connection URL (e.g., MongoDB Atlas string) |

*Note: Render automatically injects `PORT` into the runtime environment. Do NOT add `PORT` or other variables to `.env`.*

---

## 🚀 Quick Start (Local / VPS)

### Prerequisites
- Python 3.12+
- Docker Engine installed & running
- MongoDB instance (local or MongoDB Atlas)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/docker-deploy-manager.git
   cd docker-deploy-manager
   ```

2. **Set up virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/venv/activate  # On Linux/macOS
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   ```

5. **Run application**:
   ```bash
   python main.py
   ```

---

## 🐳 Running via Docker

Build and start the application container (mounting Docker socket if deploying target containers on host):

```bash
docker build -t docker-deploy-manager .

docker run -d \
  --name docker-deploy-manager \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --env-file .env \
  -p 8080:8080 \
  docker-deploy-manager
```

---

## 🤖 Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome screen & bot instructions |
| `/deploy` | Upload a new repository ZIP file for deployment |
| `/status` | View all deployed projects, status, and control panel |
| `/logs` | Select a project to view or download Docker container logs |
| `/restart` | Restart a project's container |
| `/pause` | Pause/stop a running project |
| `/stop` | Stop a project |
| `/startproject` | Start a stopped project |
| `/replace` | Replace an existing project's ZIP with safe fallback |
| `/env` | Upload/update a project's `.env` configuration |
| `/redeploy` | Rebuild & redeploy a project from stored source |
| `/remove` | Remove a project, container, image, and data |

---

## 📦 ZIP File Requirements

Each uploaded ZIP file must contain a `Dockerfile`.

Example structure A:
```
my-bot.zip
├── Dockerfile
├── requirements.txt
└── main.py
```

Example structure B:
```
my-bot.zip
└── my-bot/
    ├── Dockerfile
    ├── requirements.txt
    └── main.py
```

---

## 🛡️ Security & Integrity

- **ZIP Safety**: Validates file count, total uncompressed size, and blocks `..` path traversal attempts.
- **Admin Isolation**: Unauthenticated users cannot interact with or view deployments.
- **Masked Secrets**: Environment secret values are masked in Telegram messages and never committed into Docker builds.
