# Telegram Forward & Watermark Bot

A powerful Telegram bot designed for automated message forwarding with custom buttons, Unicode caption filtering, and advanced image watermarking.

## Features

### 🚀 Advanced Forwarding
- **String Session Support (`/ss`):** Securely use your own Telegram account for forwarding. Access private channels and restricted content.
- **Range Forwarding (`/forward`):** Cleanly copy a range of messages between any two links.
- **Reposting:** All forwarded messages are "reposted" (copied) to the target channel, removing the original forward attribution.
- **Interactive Mode:**
  - **Auto Mode:** Uses pre-configured button names (from `/auto`) and prompts for links.
  - **Manual Mode:** Fully customize buttons (names, links, rows) for individual posts.
- **Unicode Filtering:** Filter content by specific text in any language (Telugu, Hindi, Tamil, English, etc.) within captions or filenames.
- **Media Group Support:** Correct handling of albums (multiple photos/videos).
- **Trace Mode:** Real-time monitoring of source channels to automatically forward new posts as they arrive.

### 🔘 Button Management
- **Persistent Setup (`/auto`):** Configure default button names and row layouts once and reuse them during forwarding.
- **Interactive UI:** Guided setup flows for all configurations.

### 🖼️ TEdit (Image Watermarking)
- **Automatic Monitoring:** Auto-watermark new posts in monitored channels.
- **Multiple Watermark Types:** Support for Logos (images), Stickers, and Custom Text.
- **Dynamic Styling:** Configure font size, position, transparency, and color.
- **Proportional Scaling:** Watermarks automatically scale based on the source image dimensions.

### 🛠️ Utilities
- **Font Stylizer:** Apply various Unicode fonts to text.
- **Text Replacer:** Strict, multi-pass text replacement logic for captions.
- **Auto Join:** Automatically joins source channels using invite links.
- **FloodWait Protection:** Intelligent retry logic for Telegram API limits.

## Installation

### Prerequisites
- Python 3.12+
- MongoDB
- Telegram API ID and Hash (from [my.telegram.org](https://my.telegram.org))
- Bot Token (from [@BotFather](https://t.me/BotFather))

### Local Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/username/forward-bot.git
   cd forward-bot
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file based on `.env.example`:
   ```env
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   MONGO_URI=your_mongodb_uri
   ```
4. Run the bot:
   ```bash
   python -m bot
   ```

## Usage

### Commands
- `/start` - Start the bot.
- `/ss <session>` - Save your Pyrogram String Session.
- `/auto` - Configure default button names and layout.
- `/forward` - Start the range forwarding wizard.
- `/tedit` - Access the watermarking setup menu.
- `/replace` - Configure text replacement rules.
- `/font` - Stylize text with custom fonts.

## Deployment
This bot is Docker-ready and can be deployed on platforms like Render, Heroku, or VPS.
Refer to `Dockerfile` and `render.yaml` for configuration.

## License
MIT License
