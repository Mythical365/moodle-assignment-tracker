import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

SUPABASE_URL = "https://your-project.supabase.co"  # owner's Supabase project
SUPABASE_KEY = "your-anon-key"                      # owner's Supabase anon key
USER = os.environ.get("MOODLE_USERNAME", "unknown")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def init_db():
    pass  # Supabase table is created in the dashboard


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(item_id):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/seen_items?id=eq.{USER}_{item_id}&select=*",
        headers=HEADERS,
    )
    data = res.json()
    if not isinstance(data, list):
        logger.error("Supabase _get error for %s: %s", item_id, data)
        return None
    return data[0] if data else None


def _upsert(item_id, item_type, due_date, name, course_name):
    """Insert or update a row. Never touches the `reminded` column so it
    keeps its value on updates."""
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/seen_items",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
        json={
            "id": f"{USER}_{item_id}",
            "user": USER,
            "item_type": item_type,
            "due_date": due_date,
            "name": name,
            "course_name": course_name,
        },
    )
    if res.status_code not in (200, 201):
        logger.error("Supabase _upsert failed for %s (HTTP %d): %s", item_id, res.status_code, res.text)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

def check_assignment(assignment_id, due_date):
    row = _get(f"assign_{assignment_id}")
    if not row:
        return "new"
    if row["due_date"] != due_date:
        return "reactivated"
    return None


def save_assignment(a):
    _upsert(
        f"assign_{a['id']}", "assignment",
        a.get("duedate", 0),
        a["name"], a.get("_course_name", ""),
    )


# ---------------------------------------------------------------------------
# Quizzes
# ---------------------------------------------------------------------------

def check_quiz(quiz_id, close_time):
    row = _get(f"quiz_{quiz_id}")
    if not row:
        return "new"
    if row["due_date"] != (close_time or 0):
        return "reactivated"
    return None


def save_quiz(q, course_id, course_name):
    _upsert(
        f"quiz_{q['id']}", "quiz",
        q.get("timeclose", 0),
        q["name"], course_name,
    )


# ---------------------------------------------------------------------------
# Resources (uploaded files / folders)
# ---------------------------------------------------------------------------

def check_resource(module_id, timemodified):
    row = _get(f"resource_{module_id}")
    if not row:
        return "new"
    if row["due_date"] != (timemodified or 0):
        return "updated"
    return None


def save_resource(r):
    _upsert(
        f"resource_{r['id']}", "resource",
        r.get("timemodified", 0),
        r["name"], r.get("_course_name", ""),
    )


# ---------------------------------------------------------------------------
# Forum / announcement posts
# ---------------------------------------------------------------------------

def check_forum_post(discussion_id):
    return "new" if not _get(f"forum_{discussion_id}") else None


def save_forum_post(d):
    _upsert(
        f"forum_{d['id']}", "forum",
        d.get("created", 0),
        d.get("name", ""), d.get("_course_name", ""),
    )


# ---------------------------------------------------------------------------
# Due-date reminders
# ---------------------------------------------------------------------------

def get_items_due_soon():
    """Return assignments and quizzes due within 24h that haven't been reminded yet."""
    now = int(time.time())
    window = now + 86400

    assignments, quizzes = [], []
    for item_type in ("assignment", "quiz"):
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/seen_items"
            f"?user=eq.{USER}"
            f"&item_type=eq.{item_type}"
            f"&due_date=gt.{now}"
            f"&due_date=lte.{window}"
            f"&reminded=eq.false"
            f"&select=*",
            headers=HEADERS,
        )
        bucket = assignments if item_type == "assignment" else quizzes
        bucket.extend(res.json())

    return assignments, quizzes


def mark_reminded(item_id):
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/seen_items?id=eq.{item_id}",
        headers=HEADERS,
        json={"reminded": True},
    )
