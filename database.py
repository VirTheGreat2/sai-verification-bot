import sqlite3
from typing import Optional, Tuple

DB_NAME = "verified_students.db"

def init_db() -> None:
    """
    Initializes the database and creates the users table.
    
    The table contains:
    - discord_id (TEXT, Primary Key)
    - student_id (TEXT, Unique, nullable)
    - strikes (INTEGER, default 0)
    - is_locked (BOOLEAN, default 0)
    - timestamp (TEXT, default CURRENT_TIMESTAMP)
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY,
                student_id TEXT UNIQUE,
                strikes INTEGER DEFAULT 0,
                is_locked BOOLEAN DEFAULT 0,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def add_verified_user(discord_id: str, student_id: str) -> None:
    """
    Saves a successful verification.
    Inserts a new record or updates student_id and resets strikes/is_locked if re-verifying.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (discord_id, student_id, timestamp)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id) DO UPDATE SET
                student_id = excluded.student_id,
                timestamp = CURRENT_TIMESTAMP
        """, (discord_id, student_id))
        conn.commit()

def is_student_id_used(student_id: str) -> bool:
    """
    Returns True if the student_id exists and is linked to a discord_id.
    Since student_id is unique, any existence implies it is used.
    """
    if not student_id:
        return False
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT discord_id FROM users WHERE student_id = ?", (student_id,))
        row = cursor.fetchone()
        return row is not None

def get_user_state(discord_id: str) -> Optional[Tuple[int, bool]]:
    """
    Returns the user's strike count and lock status.
    Returns (strikes, is_locked) or None if the user does not exist.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT strikes, is_locked FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if row is not None:
            return row[0], bool(row[1])
        return None

def add_strike(discord_id: str) -> None:
    """
    Increments the user's strike count.
    If strikes reach 2, sets is_locked to True.
    Creates user record with 1 strike if user does not exist.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT strikes FROM users WHERE discord_id = ?", (discord_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("""
                INSERT INTO users (discord_id, strikes, is_locked, timestamp)
                VALUES (?, 1, 0, CURRENT_TIMESTAMP)
            """, (discord_id,))
        else:
            new_strikes = row[0] + 1
            is_locked = 1 if new_strikes >= 2 else 0
            cursor.execute("""
                UPDATE users
                SET strikes = ?, is_locked = ?
                WHERE discord_id = ?
            """, (new_strikes, is_locked, discord_id))
        conn.commit()

def unlock_user(discord_id: str) -> None:
    """
    Resets strikes to 0 and is_locked to False (for staff use).
    Does nothing if the user does not exist.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET strikes = 0, is_locked = 0
            WHERE discord_id = ?
        """, (discord_id,))
        conn.commit()
