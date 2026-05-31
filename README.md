# Ultimate Telegram File Sequencer & Replace Bot

A professional, production-ready Telegram bot for sequencing files and replacing text across message ranges.

## Features

- **File Sequencing**: Automatically sort collected files by Season, Quality, and Episode.
- **Bulk Replace**: Replace text, links, and button URLs across a range of messages.
- **Asynchronous**: Built with Pyrogram and Motor for high performance.
- **Database Support**: Uses MongoDB for persistence.
- **Production Ready**: Dockerized and optimized for Render deployment.

## Commands

- `/start` - Get started and see available commands.
- `/sequence` - Enter collection mode to send files for sorting.
- `/replace` - Start the step-by-step text replacement workflow.
- `/done` - Finish file collection in sequence mode.

## Environment Variables

- `BOT_TOKEN`: Your Telegram Bot Token.
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `MONGO_URI`: Your MongoDB Connection String.
- `LOG_CHANNEL`: ID of the channel for logs.
- `OWNER_ID`: Your Telegram User ID.
- `PORT`: Port for the health check server (default: 8080).
- `REPLACE_TEXT_CHANNELS`: Comma-separated list of channel IDs authorized for text replacement.

## Features
- **Health Check**: Built-in HTTP server for deployment platforms like Render.
- **Channel Security**: Only allows text replacement in specified channels.

1. **Fork** this repository.
2. Create a **MongoDB** database (e.g., on MongoDB Atlas).
3. Get your **Telegram credentials** from [my.telegram.org](https://my.telegram.org).
4. Create a **Render account**.
5. Create a new **Web Service** (or Worker) on Render.
6. Connect your **GitHub repository**.
7. Configure the **Environment Variables** in the Render dashboard.
8. **Deploy** the service.

## Local Usage

1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`.
3. Create a `.env` file based on `.env.example`.
4. Run the bot: `python -m bot.bot`.

## Docker Usage

1. Build the image: `docker build -t telegram-bot .`.
2. Run the container: `docker run --env-file .env telegram-bot`.

## Sorting Rules

The bot sorts files based on:
1. **Season** (Ascending)
2. **Quality** (240p to 2160p)
3. **Episode** (Ascending)

Metadata is extracted from captions first, then filenames as a fallback.
