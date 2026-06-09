# Ultimate Telegram Forward & Replacement Bot

A professional, production-ready Telegram bot for bulk message forwarding, text replacement, and advanced channel management. Optimized for stability and security.

## Features

- **Advanced Forwarding**:
    - Bulk forward messages between channels.
    - Support for **String Sessions** to bypass bot limitations.
    - **Interactive Mode**: Choose between Auto and Manual button attachment for each post.
    - **Caption Filtering**: Filter posts by text (supports all languages: English, Telugu, Hindi, Tamil, etc.).
    - **No Forward Tag**: All messages are reposted without forward attribution.
    - Automatic FloodWait handling and retries.
- **Auto Buttons**:
    - Pre-configure button names and row layouts with `/auto`.
    - Quickly attach links during forwarding in Auto Mode.
- **Bulk Replacement**:
    - Replace text, links, and usernames across channels using `/replace`.
    - Domain-wide replacement with `/replace_domain` (Owner only).
- **File Sequencing & Sorting**:
    - Collect and sort files by Quality, Episode, and Season using `/sequence` and `/sort`.
- **Font Styling**:
    - Apply Unicode font styles to messages or entire channels with `/font` and `/fontchannel`.
- **Search & Indexing**:
    - Index channels and search with fuzzy matching using `/search`.
- **TEdit (Logo/Watermark)**:
    - Automatically apply text, image, or sticker watermarks to new channel posts.
- **Auto Approve**:
    - Automatically accept join requests for your channels.

## Commands

### Forwarding & Sessions
- `/ss <session>` - Save a Pyrogram String Session for forwarding.
- `/forward` - Start the bulk forwarding setup wizard.
- `/auto` - Configure default button names and layout.

### Content Management
- `/sequence` - Enter collection mode to send files for sorting.
- `/sort` - Sort collected files and deliver them to a target.
- `/replace` - Start bulk text/link replacement.
- `/replace_domain` - Perform domain-wide replacement.

### Styling & Tools
- `/font <link>` - Apply Unicode font style to a range of messages.
- `/fontchannel` - Set default font for a channel.
- `/tedit` - Configure image watermarking for a channel.
- `/autoapprove` - Toggle auto-approval for join requests.
- `/redirect <url>` - Retrieve the final destination of a shortened link.

### Admin & Indexing
- `/search <query>` - Search indexed content.
- `/setchannel <id>` - Set source channel for indexing.
- `/reindex` - Rescan source channel for content.

## Setup & Deployment

### Environment Variables
- `BOT_TOKEN`: Your Telegram Bot Token.
- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `MONGO_URI`: Your MongoDB Connection String.
- `OWNER_ID`: Your Telegram User ID.
- `ADMINS`: Comma-separated list of authorized Admin IDs.
- `LOG_CHANNEL`: ID of the channel for logs.
- `PORT`: Port for health check (default: 8080).

### Deployment
1. Create a MongoDB database.
2. Deploy the Dockerfile or run `python3 -m bot.bot`.
3. Ensure the bot is an administrator in all source and target channels with "Edit Messages" and "Post Messages" permissions.

## Stability & Performance
The bot uses a queue-based worker system to handle large forwarding and watermarking jobs. It automatically handles Telegram's API limits (FloodWait) and retries failed operations to ensure 100% delivery.
