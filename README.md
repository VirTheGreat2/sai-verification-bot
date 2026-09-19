# ALPHA ORG SAI Verification Bot

Automated, high-throughput student verification bot for the STI College Ortigas-Cainta community Discord server.

---

## 1. Project Overview & Business Value

- **Name**: ALPHA ORG SAI Verification Bot
- **Purpose**: A drop-in, automated replacement for the "Appy" bot used in the STI College Ortigas-Cainta community Discord server.
- **Problem Solved**: Replaces a 12+ hour manual document verification bottleneck with a <5 second AI-driven automated pipeline, while perfectly mimicking the existing UI/UX so server staff don't have to learn a new workflow.

---

## 2. Core Architecture & Enterprise Features

- **Asynchronous Processing**: Uses an `asyncio.Queue` background worker to handle peak enrollment traffic (e.g., September rush) sequentially, preventing OOM crashes and API rate limits.
- **Memory & CDN Optimization**: On-the-fly PIL image compression (max 2048x2048, 85% JPEG quality) keeps RAM usage flat. Bypasses Discord's 24-hour CDN expiration by re-uploading optimized bytes natively.
- **Zero-PII Liability**: Extracts Student IDs via Gemini Vision but strictly hashes them using SHA-256 before SQLite storage.
- **High-Concurrency Database**: SQLite runs in WAL (Write-Ahead Logging) mode to prevent database locks.
- **Resilient AI Engine**: Uses `itertools.cycle` for multi-key rotation and dynamically cascades Gemini Flash models to prevent deprecation crashes.
- **Persistent UI**: Utilizes Discord persistent views so buttons (Staff Accept/Deny, DM Gatekeeper) survive server reboots.

---

## 3. Security & Anti-Exploit System

The bot implements a robust 3-tier security architecture:

1. **Database Duplicate Catching**: Compares SHA-256 hashes of extracted Student IDs against stored hashes to prevent students from re-using or sharing Student Assessment Invoices (SAIs).
2. **2-Strike Lockout System**: Accumulating 2 failed verification attempts automatically locks out the user and forwards their submission to server staff for manual review, preventing API spam and brute-force attempts.
3. **Strict File Type & Size Filtering**: Enforces valid mime-types (`image/jpeg`, `image/png`, `image/webp`) and restricts uploaded attachments to under 25MB before processing.

---

## 4. Setup & Deployment Instructions

### Prerequisites
- **Python 3.10+**
- **Discord Developer Portal Intents**: Enable **Message Content Intent** and **Server Members Intent**.

### Environment Variables
Create a `.env` file in the project root (or inside `reference_images/.env`) with the following variables:

```env
DISCORD_TOKEN=your_discord_bot_token_here
GEMINI_API_KEYS=key1,key2,key3
GUILD_ID=123456789012345678
VERIFY_CHANNEL_ID=123456789012345678
PENDING_CHANNEL_ID=123456789012345678
VERIFIED_ROLE_ID=123456789012345678
SUPPORT_ROLE_ID=123456789012345678
```

### Reference Images Requirement
Place valid baseline document templates (e.g., sample Student Assessment Invoices) inside the `reference_images/` directory. The AI engine uses these images to visually match table grids and document layouts.

### Running the Bot
```bash
# Run unit tests
python3 -m unittest discover

# Start the bot
python3 bot.py
```

### ⚠️ Cloud Hosting Warning
When hosting on platforms such as Render, Railway, or Fly.io, you **must** mount a **Persistent Volume/Disk** to the directory containing `verified_students.db`. Ephemeral containers wipe local files on reboot or redeploy, which would destroy the SQLite database and lockout history if not persisted.
