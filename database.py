import os
import time
import logging

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


def _connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    """Create the tracker table if it does not exist yet."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_items (
                    id TEXT PRIMARY KEY,
                    item_type TEXT NOT NULL,
                    due_date BIGINT NOT NULL DEFAULT 0,
                    name TEXT NOT NULL DEFAULT '',
                    course_name TEXT NOT NULL DEFAULT '',
                    reminded BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )


def _get(item_id):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, item_type, due_date, name, course_name, reminded
                FROM seen_items
                WHERE id = %s
                """,
                (item_id,),
            )
            return cur.fetchone()


def _upsert(item_id, item_type, due_date, name, course_name):
    """Insert or update a row without changing the reminded flag."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO seen_items
                    (id, item_type, due_date, name, course_name)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    item_type = EXCLUDED.item_type,
                    due_date = EXCLUDED.due_date,
                    name = EXCLUDED.name,
                    course_name = EXCLUDED.course_name
                """,
                (
                    item_id,
                    item_type,
                    due_date or 0,
                    name or "",
                    course_name or "",
                ),
            )


def check_assignment(assignment_id, due_date):
    row = _get(f"assign_{assignment_id}")
    if not row:
        return "new"
    if row["due_date"] != (due_date or 0):
        return "reactivated"
    return None


def save_assignment(a):
    _upsert(
        f"assign_{a['id']}",
        "assignment",
        a.get("duedate", 0),
        a["name"],
        a.get("_course_name", ""),
    )


def check_quiz(quiz_id, close_time):
    row = _get(f"quiz_{quiz_id}")
    if not row:
        return "new"
    if row["due_date"] != (close_time or 0):
        return "reactivated"
    return None


def save_quiz(q, course_id, course_name):
    _upsert(
        f"quiz_{q['id']}",
        "quiz",
        q.get("timeclose", 0),
        q["name"],
        course_name,
    )


def check_resource(module_id, timemodified):
    row = _get(f"resource_{module_id}")
    if not row:
        return "new"
    if row["due_date"] != (timemodified or 0):
        return "updated"
    return None


def save_resource(r):
    _upsert(
        f"resource_{r['id']}",
        "resource",
        r.get("timemodified", 0),
        r["name"],
        r.get("_course_name", ""),
    )


def check_forum_post(discussion_id):
    return "new" if not _get(f"forum_{discussion_id}") else None


def save_forum_post(d):
    _upsert(
        f"forum_{d['id']}",
        "forum",
        d.get("created", 0),
        d.get("name", ""),
        d.get("_course_name", ""),
    )


def get_items_due_soon():
    """Return assignments and quizzes due within 24h that haven't been reminded yet."""
    now = int(time.time())
    window = now + 86400

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, item_type, due_date, name, course_name, reminded
                FROM seen_items
                WHERE item_type = %s
                  AND due_date > %s
                  AND due_date <= %s
                  AND reminded = FALSE
                """,
                ("assignment", now, window),
            )
            assignments = cur.fetchall()

            cur.execute(
                """
                SELECT id, item_type, due_date, name, course_name, reminded
                FROM seen_items
                WHERE item_type = %s
                  AND due_date > %s
                  AND due_date <= %s
                  AND reminded = FALSE
                """,
                ("quiz", now, window),
            )
            quizzes = cur.fetchall()

    return assignments, quizzes


def mark_reminded(item_id):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE seen_items SET reminded = TRUE WHERE id = %s",
                (item_id,),
            )
