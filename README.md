# Telegram Forward & Watermark Bot

A production-grade Telegram bot architected for high-performance message forwarding, real-time channel monitoring, and professional watermarking.

## 🚀 Key Features

### 🏢 Professional Forwarding System (Admin Only)
A dedicated, high-performance module for large-scale content migration and management using a personal Telegram account.
- **Admin Authentication (`/login`):** Secure login with support for OTP and Two-Step Verification (2FA). Sessions are saved securely in MongoDB.
- **Session Persistence:** Login once; the session survives bot restarts, server reboots, and redeployments.
- **Range Forwarding (`/forward`):** Copy thousands of messages between any two links with no forward attribution.
- **Interactive Filter Grid:** Choose exactly what to forward via a toggleable UI:
  - **Media:** 🖼 Photos, 🎥 Videos, 📦 Documents, 📁 Files, 🎵 Audio, 🎤 Voice, 🎬 Animations, 😀 Stickers, 🎥 Video Notes.
  - **Content:** 📝 Text Messages, 🔗 Links (URLs), 📊 Polls, 📍 Locations, 👤 Contacts.
  - **Structure:** 📚 Albums (Media Groups).
  - **Presets:** ✅ Select All, ❌ Clear All, 🌐 All Media.
- **"No Touch" Policy:** Preserves 100% of original formatting, captions, entities, spoilers, and media quality.
- **Smart Resumption:** Automatically resumes active jobs if interrupted. Never starts from the beginning.
- **Live Progress:** Dynamic tracking of speed (msg/s), success/fail/skip counts, and ETA.
- **Control:** Immediately stop jobs with `/forwardstop` or `/logout`.

### 📤 Standard & Interactive Forwarding
- **String Session Support (`/ss`):** Use personal accounts for standard interactive tasks.
- **Interactive Wizard:** Repost media with custom button templates.
- **Unicode Filtering:** Precision filtering across all languages.
- **Trace Mode:** Real-time monitoring and auto-forwarding of new posts.

### 🖼️ TEdit (Image Watermarking)
- **Automatic Monitoring:** Auto-watermark new posts in monitored channels.
- **Dynamic Styling:** Custom logos, stickers, or text with control over position, opacity, size, and rotation.

### 🛠️ Advanced Utilities
- **Auto Join:** Automatically joins source channels via invite links.
- **Text Replacer:** Strict, multi-pass logic for caption cleaning.
- **Font Stylizer:** Transform text using unique Unicode fonts.
- **Auto Approve:** Automatically accept user join requests.

## 🛠️ Installation

### Prerequisites
- Python 3.12+
- MongoDB
- Telegram API ID and Hash ([my.telegram.org](https://my.telegram.org))
- Bot Token ([@BotFather](https://t.me/BotFather))

### Deployment
1. **Clone & Install:**
   ```bash
   git clone https://github.com/username/forward-bot.git
   cd forward-bot
   pip install -r requirements.txt
   ```
2. **Environment Setup:** Create a `.env` file:
   ```env
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   MONGO_URI=your_mongodb_uri
   ADMINS=12345,67890
   OWNER_ID=12345
   ```
3. **Run:**
   ```bash
   python -m bot.bot
   ```

## 🎮 Command Reference

### Admin & Professional
- `/login` - Start the professional account login flow.
- `/logout` - Disconnect admin account, stop all jobs, and clear session.
- `/forward` - Launch the setup wizard with interactive filter selection.
- `/forwardstop` - Stop all active professional forwarding jobs.
- `/stats` - View system statistics and active tasks.

### General
- `/ss <session>` - Save a Pyrogram String Session.
- `/auto` - Configure default button templates.
- `/scrab` - Extract buttons from a message link.
- `/tedit` - Watermarking configuration menu.
- `/cancel` - Abort any active setup wizard.
- `/stop` - Terminate standard forwarding jobs.

## 📄 License
MIT License
