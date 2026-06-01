# Ultimate Telegram File Sequencer & Search Bot

A professional, production-ready Telegram bot for sequencing files, bulk text replacement (Userbot-powered), and advanced channel indexing/searching.

## Features

- **Advanced Search**: Index entire channels using a Userbot and search with fuzzy matching.
- **Quality Grouping**: Search results are automatically grouped by quality (480p, 720p, 1080p, 2160p).
- **Batch Links**: Generates batch links for indexed series and episodes.
- **Userbot Replacement**: Bulk replace text, links, and usernames across channels using a Userbot.
- **File Sequencing**: Automatically sort collected files by Season, Quality, and Episode.
- **Production Ready**: Asynchronous architecture, MongoDB persistence, and Dockerized.
- **Health Check**: Built-in HTTP server for deployment platforms like Render.

## Commands

### User Commands
- `/start` - Get started and see available commands.
- `/search <query>` - Search indexed content (e.g., `/search Naruto S01`).
- `/sequence` - Enter collection mode to send files for sorting.
- `/replace` - Start the bulk text/link replacement workflow.
- `/replace_domain` - Perform domain-wide replacement (Owner only).
- `/cancel_replace` - Cancel an active domain replacement task.

### Admin Commands
- `/setchannel <id>` - Set the source channel for indexing.
- `/setbot <username>` - Set the batch bot username for search links.
- `/reindex` - Scan or rescan the source channel for content.

## Environment Variables

- `BOT_TOKEN`: Your Telegram Bot Token.
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `MONGO_URI`: Your MongoDB Connection String.
- `STRING_SESSION`: Pyrogram String Session for the Userbot.
- `OWNER_ID`: Your Telegram User ID.
- `ADMINS`: Comma-separated list of authorized Admin IDs.
- `LOG_CHANNEL`: ID of the channel for logs.
- `PORT`: Port for health check (default: 8080).
- `REPLACE_TEXT_CHANNELS`: Comma-separated list of authorized channel IDs for replacement.

## Deployment on Render

1. **Fork** this repository.
2. Create a **MongoDB** database.
3. Get a **String Session** for your user account.
4. Create a new **Web Service** on Render.
5. Connect your repository and configure the environment variables.
6. The bot will automatically start the health check server on the assigned port.

## Sorting & Search Logic

The bot extracts metadata (Season, Episode, Quality) using optimized regex and groups search results by quality with priority: `480p > 720p > 1080p > 2160p`.
The `/replace` command uses the Userbot client to allow edits in restricted channels or where the bot itself lacks permissions.
