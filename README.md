# 🚀 Production-Grade Telegram Forwarding Bot

A powerful and scalable Telegram Forwarding Bot built with Pyrogram and MongoDB.

## ✨ Features

- **✅ Multi-Step Forwarding Wizard:** Intuitive flow to select message ranges and targets.
- **📂 Message Filtering:** Toggle between Photos, Videos, Documents, Audio, and more.
- **🔐 Secure Login:** Admin-only login with OTP and 2FA support using String Sessions.
- **📊 Real-time Progress:** Live updates with speed, ETA, and progress bar.
- **🛡 Production Ready:** Asynchronous, error-resilient, and Docker-ready.
- **🔌 Modular Architecture:** Easily extendable plugin system.

## 🛠 Installation

### 1. Local Deployment

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file based on `.env.example`.
4. Run the bot:
   ```bash
   python -m bot.bot
   ```

### 2. Docker Deployment

1. Clone the repository.
2. Configure `.env`.
3. Start with Docker Compose:
   ```bash
   docker-compose up --build -d
   ```

## ⚙️ Environment Variables

- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `BOT_TOKEN`: Your Telegram Bot Token.
- `MONGO_URI`: MongoDB connection string.
- `ADMINS`: Comma-separated list of admin user IDs.

## 🤖 Commands

- `/start`: Start the bot.
- `/help`: Display help message.
- `/login`: Securely log in your Telegram account.
- `/logout`: Remove your session.
- `/forward`: Start the forwarding wizard.
- `/forwardstop`: Stop an active forwarding task.
- `/stats`: View bot usage statistics.
- `/ping`: Check bot latency.

## 🤝 Troubleshooting

- **Peer ID Invalid:** Ensure the bot/account has accessed the chat recently.
- **FloodWait:** Telegram is rate-limiting you. The bot handles this automatically.
- **Session Expired:** Re-login using `/login`.

## 📄 License

MIT License.
