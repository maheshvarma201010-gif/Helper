# Ultimate Telegram File Sequencer & Replacement Bot (Bot-Only Version)

A professional, production-ready Telegram bot for sequencing files, bulk text replacement, and advanced channel font styling. This version is optimized for stability and uses only the official Telegram Bot API (no Userbot required).

## Features

- **File Sequencing**: Automatically sort collected files by Season, Quality, and Episode.
- **Bulk Replacement**: Replace text, links, and usernames across channels.
- **Font Styling**:
    - `/font <link>`: Apply Unicode font styles to a range of messages (e.g., `https://t.me/c/123/10-20`).
    - `/fontchannel`: Set a default font for all new posts in a channel.
- **Search & Indexing**: Index channels and search with fuzzy matching.
- **Production Ready**: Asynchronous architecture, MongoDB persistence, and Dockerized.
- **Health Check**: Built-in HTTP server for deployment platforms like Render.

## Commands

### User Commands
- `/start` - Get started and see available commands.
- `/search <query>` - Search indexed content.
- `/sequence` - Enter collection mode to send files for sorting.
- `/replace` - Start the bulk text/link replacement workflow.
- `/replace_domain` - Perform domain-wide replacement (Owner only).
- `/font <message_link>` - Apply a Unicode font style to a range of messages.
- `/fontchannel <channel_id>` - Set a default Unicode font for a channel.
- `/redirect <url>` - Follow all HTTP redirects and retrieve the final destination URL.

### Admin Commands
- `/setchannel <id>` - Set the source channel for indexing.
- `/setbot <username>` - Set the batch bot username for search links.
- `/reindex` - Scan or rescan the source channel for content.
- `/verify` - Verify bot access and permissions in configured channels.

## Environment Variables

- `BOT_TOKEN`: Your Telegram Bot Token.
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `MONGO_URI`: Your MongoDB Connection String.
- `OWNER_ID`: Your Telegram User ID.
- `ADMINS`: Comma-separated list of authorized Admin IDs.
- `LOG_CHANNEL`: ID of the channel for logs.
- `PORT`: Port for health check (default: 8080).
- `REPLACE_TEXT_CHANNELS`: Comma-separated list of authorized channel IDs for replacement.

## Deployment on Render

1. **Fork** this repository.
2. Create a **MongoDB** database.
3. Create a new **Web Service** on Render.
4. Connect your repository and configure the environment variables.
5. The bot will automatically start the health check server on the assigned port.

## Note on Permissions
Since this bot does not use a Userbot, it **MUST** be an administrator in any channel it needs to index, edit, or stylize. It needs "Edit Messages" and "Post Messages" permissions.
