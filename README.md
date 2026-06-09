# Ultimate Telegram Forward & Management Bot

A professional, production-ready Telegram bot for bulk message forwarding, text replacement, real-time channel tracing, and advanced management. Optimized for stability, security, and high-volume tasks.

## 🚀 Features

- **Advanced Forwarding**:
    - Bulk forward messages using **String Sessions** to bypass bot API limits.
    - **Interactive Mode**: Choose between Auto and Manual button attachment for each post.
    - **Media Group Support**: Correct handling of albums and media groups.
    - **Caption Filtering**: Filter posts by text (supports all Unicode languages: English, Telugu, Hindi, Tamil, etc.).
    - **No Forward Tag**: All messages are reposted as new messages using `copy_message`.
    - Automatic FloodWait handling and retries.
- **Trace Mode (Real-Time)**:
    - Automatically monitor source channels for new messages and forward them instantly to targets.
    - Trace tasks survive bot restarts and maintain filter/button rules.
- **Auto Button Templates**:
    - Pre-configure button names and row layouts with `/auto`.
    - Attach links during forwarding with a single click.
- **Bulk Replacement**:
    - Replace text, links, and usernames across channels using `/replace`.
    - Domain-wide replacement with `/replace_domain` (Owner only).
- **TEdit (Image Watermarking)**:
    - Automatically apply text, image, or sticker watermarks to new channel posts.
- **Auto Approve**:
    - Automatically accept join requests for your channels via `/autoapprove`.
- **Search & Indexing**:
    - Index channels and search with fuzzy matching using `/search`.

## 🛠 Commands

### Forwarding & Sessions
- `/ss <session>` - Store a Pyrogram String Session for all operations.
- `/forward` - Start the bulk forwarding setup wizard.
- `/auto` - Configure default button names and layout templates.

### Real-Time Monitoring
- `/stats` - (Admin Only) View active forwarding jobs, trace tasks, and session counts.
- Trace Mode is initiated interactively after a `/forward` job completes.

### Content & Management
- `/sequence` - Enter collection mode to send files for sorting.
- `/sort` - Sort collected files and deliver them to a target.
- `/replace` - Start bulk text/link replacement.
- `/tedit` - Configure image watermarking for a channel.
- `/autoapprove` - Toggle auto-approval for join requests.

## ⚙️ Setup & Deployment

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
2. Configure environment variables in `.env`.
3. Deploy using Docker or run `python3 -m bot.bot`.
4. Ensure the bot is an administrator in all source and target channels.

## 🛡 Stability & Security
The bot utilizes a concurrent, queue-based worker system to handle heavy tasks without blocking. It includes automatic FloodWait recovery, persistent state storage for restart survival, and authenticated user sessions for maximum reliability.
