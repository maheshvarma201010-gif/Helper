# Telegram Forward & Watermark Bot

A production-grade Telegram bot architected for high-performance message forwarding, real-time channel monitoring, and professional watermarking.

## 🚀 Key Features

### 🏢 Professional Forwarding System (Admin Only)
A dedicated, high-performance module for large-scale content migration and management.
- **Admin Authentication (`/login`):** Secure login using your own Telegram account. Supports OTP and Two-Step Verification (2FA).
- **Session Persistence:** Login once; the session is saved securely in MongoDB and survives restarts, VPS reboots, and redeployments.
- **Range Forwarding (`/forward`):** Seamlessly copy thousands of messages between any two links with no forward attribution. **Fast and efficient.**
- **Advanced Filter Selection:** Before starting, choose exactly what to forward via a toggleable inline grid:
  - Media: Photos, Videos, Documents, Files, Audio, Voice, Animations, Stickers, Video Notes.
  - Content: Text Messages, Links (URLs), Polls, Locations, Contacts.
  - Structure: Albums (Media Groups).
  - Presets: "Select All", "Clear All", "All Media".
- **Media Group Excellence:** Native handling of albums, ensuring they are posted as a single unit without duplicates or quality loss.
- **Smart Resumption:** Automatically resumes active forwarding jobs if the bot or server restarts.
- **Live Progress Tracking:** Real-time metrics including completion percentage, success/fail/skip counts, speed (msg/s), and ETA.
- **Control Management (`/forwardstop`):** Safely terminate active professional forwarding tasks at any time.

### 📤 Standard & Interactive Forwarding
- **String Session Support (`/ss`):** Use personal accounts to access restricted or private content.
- **Interactive Button Wizard:**
  - **Auto Mode:** Reposts media with pre-defined button templates (configured via `/auto`).
  - **Manual Mode:** Fully customize button names and URLs for individual posts.
- **Unicode Filtering:** Precision filtering of captions and filenames across all languages (Telugu, Hindi, Tamil, English, etc.).
- **Trace Mode:** Monitor source channels in real-time and automatically forward new posts as they arrive.

### 🖼️ TEdit (Image Watermarking)
- **Automated Monitoring:** Instantly apply watermarks to new posts in monitored channels.
- **Watermark Styles:** Support for Logos, Stickers, and Custom Text.
- **Dynamic Formatting:** Full control over font size, position, transparency, and color.
- **Proportional Scaling:** Intelligent scaling ensures watermarks look perfect on images of any resolution.

### 🛠️ Advanced Utilities
- **Auto Join:** Automatically joins source channels via invite/join links.
- **Text Replacer:** Strict, multi-pass logic for cleaning and replacing text in captions.
- **Font Stylizer:** Transform text using unique Unicode fonts.
- **Auto Approve:** Automatically accept user join requests in managed channels.

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
- `/logout` - Disconnect your admin account and clear the session.
- `/forward` - Launch the range forwarding setup wizard (includes Filter Selection).
- `/forwardstop` - Immediately stop active professional forwarding jobs.
- `/stats` - View system-wide statistics and active tasks.

### General
- `/ss <session>` - Save a Pyrogram String Session.
- `/auto` - Configure default button templates.
- `/scrab` - Extract button data from a message link.
- `/tedit` - Open the watermarking configuration menu.
- `/cancel` - Abort any active setup wizard.
- `/stop` - Terminate standard forwarding jobs.

## 📄 License
MIT License
