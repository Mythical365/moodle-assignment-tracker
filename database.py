import os
import time
import logging

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# One connection is reused for the whole run instead of opening a new one per
# query. autocommit=True means every statement commits immediately, so we never
# sit "idle in transaction" and the Neon compute can suspend normally.
_conn = None

# All known rows, loaded with ONE query per run instead of one query per item.
# Maps id -> row dict. It is kept in sync by _upsert / mark_reminded, and
# reset_cache() forces a reload (checker.py calls it at the start of each run).
_seen = None


def reset_cache():
    global _seen
    _seen = None


def _connect():
    global _conn
    if _conn is None or _conn.closed:
        # connect_timeout covers Neon waking up from a cold start.
        _conn = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            autocommit=True,
            connect_timeout=15,
        )
    return _conn


def close_db():
    """Close the shared connection (safe to call more than once)."""
    global _conn
    if _conn is not None and not _conn.closed:
        _conn.close()
    _conn = None
    reset_cache()


def _run(sql, params=(), fetch=None):
    """Execute one statement, reconnecting once if the connection dropped.

    Every statement here is idempotent (SELECT, upsert, UPDATE ... SET flag),
    so retrying after a dropped connection is safe. In loop mode the process
    sleeps for 30 min between checks, long enough for Neon to close an idle
    connection, so this matters.
    """
    for attempt in (1, 2):
        try:
            with _connect().cursor() as cur:
                cur.execute(sql, params)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                return None
        except psycopg.OperationalError as e:
            logger.warning("DB connection problem (attempt %d/2): %s", attempt, e)
            close_db()
            if attempt == 2:
                raise
            time.sleep(2)


def init_db():
    """Create the tracker table if it does not exist yet."""
    _run(
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


def _load_seen():
    global _seen
    rows = _run(
        """
        SELECT id, item_type, due_date, name, course_name, reminded
        FROM seen_items
        """,
        fetch="all",
    )
    _seen = {r["id"]: r for r in rows}
    return _seen


def _get(item_id):
    seen = _seen if _seen is not None else _load_seen()
    return seen.get(item_id)


def _upsert(item_id, item_type, due_date, name, course_name):
    """Insert or update a row.

    `reminded` is kept on normal updates, but reset to FALSE when the due date
    changes, so a postponed deadline gets its 24h reminder again.
    """
    _run(
        """
        INSERT INTO seen_items
            (id, item_type, due_date, name, course_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            item_type = EXCLUDED.item_type,
            due_date = EXCLUDED.due_date,
            name = EXCLUDED.name,
            course_name = EXCLUDED.course_name,
            reminded = CASE
                WHEN seen_items.due_date <> EXCLUDED.due_date THEN FALSE
                ELSE seen_items.reminded
            END
        """,
        (
            item_id,
            item_type,
            due_date or 0,
            name or "",
            course_name or "",
        ),
    )

    if _seen is not None:
        prev = _seen.get(item_id)
        _seen[item_id] = {
            "id": item_id,
            "item_type": item_type,
            "due_date": due_date or 0,
            "name": name or "",
            "course_name": course_name or "",
            # Mirrors the SQL: reminded is kept unless the due date changed.
            "reminded": bool(
                prev and prev["reminded"] and prev["due_date"] == (due_date or 0)
            ),
        }


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

    rows = _run(
        """
        SELECT id, item_type, due_date, name, course_name, reminded
        FROM seen_items
        WHERE item_type IN ('assignment', 'quiz')
          AND due_date > %s
          AND due_date <= %s
          AND reminded = FALSE
        ORDER BY due_date
        """,
        (now, window),
        fetch="all",
    )

    assignments = [r for r in rows if r["item_type"] == "assignment"]
    quizzes = [r for r in rows if r["item_type"] == "quiz"]
    return assignments, quizzes


def mark_reminded(item_id):
    _run(
        "UPDATE seen_items SET reminded = TRUE WHERE id = %s",
        (item_id,),
    )

    if _seen is not None and item_id in _seen:
        _seen[item_id]["reminded"] = True
