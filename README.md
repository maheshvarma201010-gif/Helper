# Render Deployer Bot — Telegram Bot for Render & Docker Deployments

An advanced, production-ready Telegram Bot built with Python, Pyrogram, MongoDB, and the Render REST API to deploy and manage services on Render directly from Telegram.

## Features

### 🐳 Advanced Dockerfile Deployments
When user selects **🐳 Deploy with Dockerfile**:
- **NO Build or Start Commands requested**
- Render Docker runtime configuration (`env: "docker"`)
- Automatic repository Dockerfile detection and selection
- `🔍 Check Dockerfile` validation
- `🛠 Fix Dockerfile` with interactive diff preview
- `🛠 Generate Dockerfile` for repos missing a Dockerfile
- Configurable Dockerfile Path, Docker Context, and Environment Variables

### 🛠 Standard Deployments
- Interactive deployment wizard for Web Services, Background Workers, Cron Jobs, and Static Sites
- Build Command and Start Command setup
- Branch and Instance / Region configuration

### ⚙️ Environment Variables Management
- View, Add, Edit, Delete, and Bulk Import (`KEY=value`) environment variables
- Mask secret values in Telegram messages (`KEY=****123`)
- Zero disclosure of secrets, API keys, or bot tokens in logs

### 🔗 GitHub Authorization Integration
- Verifies Render & GitHub connection prior to deployment
- Direct GitHub OAuth link (`https://github.com/apps/render/installations/new`)

### 📊 Service Management & Control
- `/projects` — List connected Render services
- `/status` — View real-time status badges (`🟢 RUNNING`, `🔄 DEPLOYING`, `🟡 BUILDING`, `🔴 FAILED`, `⚪ STOPPED`)
- `/logs` — View recent deployment logs
- `/restart` — Restart service
- `/redeploy` — Trigger fresh deployment
- `/stop` — Suspend service
- `/delete` — Safely delete service with strong confirmation

## Local Setup

### Prerequisites
- Python 3.12+
- MongoDB
- Telegram API ID, Hash, and Bot Token

### Installation
1. Clone repository:
   ```bash
   git clone https://github.com/your-username/render-deployer-bot.git
   cd render-deployer-bot
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and configure credentials:
   ```env
   API_ID=123456
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   MONGO_URI=mongodb://localhost:27017/render_deployer
   ```
4. Run the bot:
   ```bash
   python -m bot.bot
   ```

## Deployment on Render

This bot itself is Docker-ready and can be deployed directly on Render using `render.yaml` or Dockerfile deployment option!

## License
MIT
