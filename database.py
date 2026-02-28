import sqlite3
import time
import logging
from config import Config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS assignments (
    id          INTEGER PRIMARY KEY,   -- Moodle assignment ID
    course_id   INTEGER NOT NULL,
    course_name TEXT NOT NULL,
    name        TEXT NOT NULL,
    due_date    INTEGER,               -- Unix timestamp (0 or NULL = no deadline)
    seen_at     INTEGER NOT NULL       -- When we first saw this item
);

CREATE TABLE IF NOT EXISTS quizzes (
    id          INTEGER PRIMARY KEY,   -- Moodle quiz ID
    course_id   INTEGER NOT NULL,
    course_name TEXT NOT NULL,
    name        TEXT NOT NULL,
    time_open   INTEGER,               -- Unix timestamp
    time_close  INTEGER,               -- Unix timestamp (this is the deadline)
    seen_at     INTEGER NOT NULL
);
"""


def get_conn():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database initialized at %s", Config.DATABASE_PATH)


def check_assignment(assignment_id, new_due_date):
    """
    Check if we should notify about this assignment.
    Returns:
      'new'         — never seen before
      'reactivated' — seen before but due date changed to a future date
      None          — already seen, no change (skip it)
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT due_date FROM assignments WHERE id = ?", (assignment_id,)
        ).fetchone()

    if row is None:
        return "new"

    old_due = row["due_date"]
    now = int(time.time())

    # If the due date changed AND the new date is in the future → reactivated
    if new_due_date and new_due_date != old_due and new_due_date > now:
        return "reactivated"

    return None


def save_assignment(a):
    """Save or update an assignment in the DB."""
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO assignments (id, course_id, course_name, name, due_date, seen_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   due_date = excluded.due_date,
                   seen_at = excluded.seen_at""",
            (
                a["id"],
                a["_course_id"],
                a["_course_name"],
                a["name"],
                a.get("duedate") or None,
                now,
            ),
        )


def check_quiz(quiz_id, new_time_close):
    """
    Check if we should notify about this quiz.
    Same logic as check_assignment but for quizzes.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT time_close FROM quizzes WHERE id = ?", (quiz_id,)
        ).fetchone()

    if row is None:
        return "new"

    old_close = row["time_close"]
    now = int(time.time())

    if new_time_close and new_time_close != old_close and new_time_close > now:
        return "reactivated"

    return None


def save_quiz(q, course_id, course_name):
    """Save or update a quiz in the DB."""
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO quizzes (id, course_id, course_name, name, time_open, time_close, seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   time_open = excluded.time_open,
                   time_close = excluded.time_close,
                   seen_at = excluded.seen_at""",
            (
                q["id"],
                course_id,
                course_name,
                q["name"],
                q.get("timeopen") or None,
                q.get("timeclose") or None,
                now,
            ),
        )
