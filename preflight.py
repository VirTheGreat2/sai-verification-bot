#!/usr/bin/env python3
"""
Pre-Flight Validation Script for SAI Verification Bot.
Validates environment variables, SQLite version, WAL mode, database permissions,
and Gemini API key validity prior to bot startup.
"""

import sys
import os
import sqlite3
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("preflight")


def check_env_variables() -> bool:
    """
    Validates required environment variables.
    Loads variables from .env and reference_images/.env.
    Checks for DISCORD_TOKEN, GEMINI_API_KEY, GUILD_ID, VERIFIED_ROLE_ID, and HMAC_SECRET_PEPPER.
    """
    load_dotenv(".env")
    load_dotenv("reference_images/.env")

    # Support GEMINI_API_KEYS by mapping first key to GEMINI_API_KEY if missing
    if not os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEYS"):
        keys = [k.strip() for k in os.environ["GEMINI_API_KEYS"].split(",") if k.strip()]
        if keys:
            os.environ["GEMINI_API_KEY"] = keys[0]

    required_vars = ["DISCORD_TOKEN", "GEMINI_API_KEY", "GUILD_ID", "VERIFIED_ROLE_ID"]
    missing = []

    for var in required_vars:
        val = os.environ.get(var)
        if not val or not val.strip():
            missing.append(var)

    pepper = os.environ.get("HMAC_SECRET_PEPPER") or os.environ.get("APP_SECRET_PEPPER") or ""
    if not pepper or not pepper.strip():
        missing.append("HMAC_SECRET_PEPPER")

    if missing:
        logger.error(f"Missing required environment variable(s): {', '.join(missing)}")
        return False

    if len(pepper.strip()) < 32:
        logger.error("HMAC_SECRET_PEPPER must meet minimum cryptographic entropy (>= 32 characters).")
        return False

    mod_log_channel = os.environ.get("MOD_LOG_CHANNEL_ID")
    if not mod_log_channel or not mod_log_channel.strip():
        logger.warning("Optional MOD_LOG_CHANNEL_ID environment variable is not set.")

    logger.info("Environment variables check passed.")
    return True


def check_database() -> bool:
    """
    Initializes database and verifies:
    1. SQLite version supports STRICT tables (>= 3.37.0)
    2. SQLite WAL mode is enabled
    3. Directory file system write permissions
    """
    try:
        if sqlite3.sqlite_version_info < (3, 37, 0):
            logger.error(f"SQLite version {sqlite3.sqlite_version} does not support STRICT tables (requires >= 3.37.0).")
            return False

        import database
        database.init_db()
        db_name = database.DB_NAME

        db_dir = os.path.dirname(os.path.abspath(db_name)) or "."
        if not os.access(db_dir, os.W_OK):
            logger.error(f"File system directory '{db_dir}' is not writable.")
            return False

        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            row = cursor.fetchone()
            
            if not row or str(row[0]).lower() != "wal":
                mode = row[0] if row else "None"
                logger.error(f"SQLite journal_mode is '{mode}', expected 'wal'.")
                return False

            # Verify write permissions by writing to a temporary test table
            cursor.execute("CREATE TABLE IF NOT EXISTS _preflight_test (id INTEGER PRIMARY KEY);")
            cursor.execute("INSERT INTO _preflight_test (id) VALUES (1) ON CONFLICT(id) DO NOTHING;")
            cursor.execute("DROP TABLE IF EXISTS _preflight_test;")
            conn.commit()

        logger.info("Database WAL mode, SQLite version, and write permissions check passed.")
        return True
    except Exception as e:
        logger.error(f"Database pre-flight check failed: {e}")
        return False


def check_gemini_api() -> bool:
    """
    Instantiates genai.Client from google-genai and executes a lightweight model ping.
    """
    try:
        from google import genai
        import ai_engine

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            keys = ai_engine.load_env_keys()
            if keys:
                api_key = keys[0]

        if not api_key:
            logger.error("No Gemini API key found for validation.")
            return False

        client = genai.Client(api_key=api_key)
        # Execute a lightweight API ping by listing models
        models = client.models.list()
        # Evaluate iterator to trigger API request
        next(iter(models), None)

        logger.info("Gemini API key verification ping passed.")
        return True
    except Exception as e:
        logger.error(f"Gemini API check failed: {e}")
        return False


def main() -> None:
    """
    Executes all pre-flight checks and exits with code 0 on success or 1 on failure.
    """
    logger.info("Starting production pre-flight validation checks...")

    env_ok = check_env_variables()
    db_ok = check_database()
    gemini_ok = check_gemini_api()

    if env_ok and db_ok and gemini_ok:
        logger.info("All pre-flight checks passed successfully.")
        sys.exit(0)
    else:
        logger.error("Pre-flight validation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
