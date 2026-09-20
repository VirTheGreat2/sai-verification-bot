# ALPHA ORG SAI Verification Bot

The ultimate "Source of Truth" for the **ALPHA ORG SAI Verification Bot** - a strictly private, professional-grade automated student verification system tailored for the STI College Ortigas-Cainta Discord server.

---

## 1. Project Overview

- **Name**: ALPHA ORG SAI Verification Bot
- **Purpose**: A seamless, automated drop-in replacement for the legacy manual "Appy" bot used in the STI College Ortigas-Cainta Discord server.
- **Impact**: Dramatically slashes the grueling **12+ hour manual document verification bottleneck down to a <5-second AI-driven pipeline**. It achieves this major optimization while preserving the exact same intuitive UI/UX for both students and staff, minimizing friction and training overhead.

---

## 2. Service Account Credentials (INTERNAL USE ONLY)

To support complete administrative takeover, here are the credentials for the dedicated Google Account created specifically to host this bot's Gemini API Keys in Google AI Studio.

> ⚠️ **CRITICAL SECURITY WARNING:** These credentials are for **INTERNAL SCHOOL USE ONLY**. Do not share these credentials outside Authorized IT Administrators.

| Field | Value |
| :--- | :--- |
| **Platform** | [Google AI Studio](https://aistudio.google.com/) |
| **Email** | `alpha.saibot.dev@gmail.com` |
| **Password** | `ALPHA2026` |

### Key Management & Rate Limits
If the bot hits API rate limits during peak enrolment periods (e.g., the high-throughput September rush), future maintainers should:
1. Log into this account at [Google AI Studio](https://aistudio.google.com/).
2. Revoke compromised or throttled keys, and generate a new `GEMINI_API_KEY`.
3. Update the `.env` file with the fresh token(s).

---

## 3. Core Architecture & Security

This codebase is designed with robustness, performance, and student privacy at its core. Below is a deep-dive into the architectural mechanics:

### ⚙️ SDK & AI Engine
- **Official SDK**: The bot integrates the official [`google-genai` SDK](https://pypi.org/project/google-genai/) via [`ai_engine.py`](ai_engine.py) for all Gemini operations.
- **Dynamic Model Discovery**: Rather than hardcoding fixed models, the bot implements [`get_active_flash_models`](ai_engine.py:79) to query the API at startup, dynamically identifying and targeting the newest available Gemini Flash models (e.g., `gemini-2.5-flash`).
- **Cascading Fallback**: In the event of an `HTTP 429` (Resource Exhausted/Rate Limit) error, the bot initiates a smart cascading fallback. It automatically rotates the active API key and cascades requests to secondary models to prevent queue deadlocks and maintain a continuous verification stream.

### 📥 Queue System
- **Memory-Flat Worker Queue**: During the extreme September enrollment rush, high traffic could easily crash standard micro-cloud containers via Out-Of-Memory (OOM) errors.
- **Implementation**: To prevent OOM crashes, [`bot.py`](bot.py) utilizes an asynchronous background worker powered by [`asyncio.Queue`](bot.py:21). Students are placed in a sequential, memory-efficient queue, ensuring that RAM usage remains flat and micro-cloud hosts remain stable.

### 🖼️ Image Optimization
- **Processing**: The system uses the Python Imaging Library ([`PIL`](ai_engine.py:5)) to dynamically compress incoming student receipt/invoice images to a maximum boundary of `2048x2048` pixels at `85%` JPEG quality via [`optimize_image`](ai_engine.py:113).
- **Discord CDN Bypass**: Since Discord's CDN attachments expire every 24 hours, the bot prevents broken images in staff review logs by optimizing the raw image bytes and re-uploading the compressed bytes natively directly to the staff review/pending channel.

### 🔒 Zero-PII Liability
- **Privacy Standard**: In compliance with local student privacy laws, raw Student IDs and personal names are never stored.
- **Implementation**: The bot normalizes the raw Student ID (converts to uppercase and strips whitespace) and immediately hashes it using [`hashlib.sha256`](database.py:17) prior to database persistence. Only this anonymous SHA-256 hash is saved, shielding the school from PII liabilities.

### 🗄️ Database
- **High Concurrency SQLite**: To ensure the bot easily handles multi-user concurrent reads and writes, the database layer in [`database.py`](database.py) runs SQLite with Write-Ahead Logging via [`PRAGMA journal_mode=WAL;`](database.py:31). This allows concurrent, lock-free operations even during peak hours.

---

## 4. Setup & Deployment (The Playbook)

Follow this precise sequence to install, configure, and safely run the verification system in production.

### Prerequisites
- Python `3.10` or higher.
- A Discord Bot account with the **Message Content Intent** and **Server Members Intent** enabled.

### Complete Directory Structure

- [`ai_engine.py`](ai_engine.py): Handles Gemini Vision API connection, model discovery, key rotation, and PIL image optimization.
- [`bot.py`](bot.py): Drives the Discord UI, slash commands, persistent views (surviving bot restarts), and the async queue worker.
- [`database.py`](database.py): Manages SQLite connection, schema creation, WAL mode configuration, and PII-safe hashing.
- [`preflight.py`](preflight.py): Performs pre-flight validations verifying environmental configurations, API health, and file permissions.
- [`requirements.txt`](requirements.txt): Lists all third-party dependencies required for execution.
- [`Procfile`](Procfile): Specifies startup instructions for PaaS platforms.
- [`.env.example`](.env.example): Complete configuration template.

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy [`.env.example`](.env.example) to `.env` and fill in the required keys:
```bash
cp .env.example .env
```

| Variable Name | Required | Description |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | **Yes** | Your Discord Bot token. |
| `GEMINI_API_KEY` | **Yes** | Primary Gemini API Key. (You can also specify multiple keys in `GEMINI_API_KEYS` comma-separated for rotation). |
| `GUILD_ID` | **Yes** | Target Discord Server Guild ID. |
| `VERIFY_CHANNEL_ID` | **Yes** | The channel ID where the `/setup-verify` menu is placed for students. |
| `PENDING_CHANNEL_ID` | **Yes** | Staff channel ID where pending manual reviews and fallback cases are posted. |
| `VERIFIED_ROLE_ID` | **Yes** | The Discord Role ID granted to students upon successful verification. |
| `SUPPORT_ROLE_ID` | **Yes** | Discord Role ID of the staff/support team allowed to execute moderator commands. |
| `MOD_LOG_CHANNEL_ID` | *Optional* | Highly recommended channel ID for routing audit/moderator logs. |

### Step 3: Run the Verification Pre-Flight Check
Before spinning up the bot, you **MUST** run the validation suite to assert database access and API key health:
```bash
python preflight.py
```

### Step 4: Run the Bot
If the preflight check succeeds, start the production bot:
```bash
python bot.py
```
*Note: The combined production startup script is:*
```bash
python preflight.py && python bot.py
```

---

### ⚠️ Essential Production Warnings

#### 1. Persistent Storage Requirement for Cloud Deployments
If you deploy this bot on PaaS hosting providers like **Render** or **Railway**, you **MUST mount a Persistent Volume** to the directory containing the SQLite database file (`verified_students.db`).
* **Why?** Cloud containers feature ephemeral filesystems. On daily restarts or code deployments, your SQLite file will be silently deleted if not on a persistent volume. This permits already-verified Student IDs to verify again under separate Discord accounts, enabling duplicate verification exploits.

#### 2. Discord Role Hierarchy Configuration
The bot's custom Discord role **MUST** be placed higher than the `Alpha Member .ᐟ` (or student role) in the Discord Server's settings hierarchy.
* **Why?** Discord API prevents bots from assigning or modifying roles that sit equal to or higher than their own highest role. Failure to position the bot's role correctly will result in `Forbidden: 403` errors whenever it attempts to grant verified roles.

---

## 5. Moderator Toolkit (Slash Commands)

The bot equips support agents (with `@Support` or Administrator privileges) with an administrative command-line toolkit to handle manual overrides, audits, and adjustments.

### 🔍 `/check-student [student_id] or [@user]`
* **Usage**: `/check-student student_id:12345` or `/check-student user:@StudentUsername`
* **Action**: Normalizes and hashes the inputs, then queries SQLite to see if the record exists.
* **Output**: Displays the registration timestamp, whether they are verified, their strike/failure counts, and the associated Discord User ID.

### 🔗 `/unlink-student [student_id] or [@user]`
* **Usage**: `/unlink-student student_id:12345` or `/unlink-student user:@StudentUsername`
* **Action**: Deletes the student's entry from the database and revokes their verified role.
* **Output**: Fully resets their verification eligibility, allowing them to restart the verification process.

### ⚡ `/force-verify [@user] [student_id]`
* **Usage**: `/force-verify user:@StudentUsername student_id:12345`
* **Action**: Instantly bypasses the AI verification pipeline. It normalizes and hashes the student ID, binds it to their Discord User ID, stores it in the database, and grants them the verified role immediately.
* **Output**: Used as a fallback when a student's document is physically degraded (torn, heavily creased, or extremely low-contrast) preventing automated AI vision parsing.

---

## 6. Development & Testing

A complete suite of tests is included to validate the AI cascading fallbacks, database transactions, preflight assertions, and Discord queue functionality.

To execute the test suite:
```bash
pytest
```

Tests automatically build and clean up temporary database environments (`*.db`, `*.db-wal`, `*.db-shm`), keeping the workspace clean.
