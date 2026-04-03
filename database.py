import os
import time
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def init_db():
    pass  # Supabase table already exists, nothing to init

def check_assignment(assignment_id, due_date):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/seen_items?id=eq.assign_{assignment_id}&select=due_date",
        headers=HEADERS
    )
    data = res.json()
    if not data:
        return "new"
    if data[0]["due_date"] != due_date:
        return "reactivated"
    return None

def save_assignment(a):
    requests.post(
        f"{SUPABASE_URL}/rest/v1/seen_items",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
        json={
            "id": f"assign_{a['id']}",
            "item_type": "assignment",
            "due_date": a.get("duedate", 0)
        }
    )

def check_quiz(quiz_id, close_time):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/seen_items?id=eq.quiz_{quiz_id}&select=due_date",
        headers=HEADERS
    )
    data = res.json()
    if not data:
        return "new"
    if data[0]["due_date"] != close_time:
        return "reactivated"
    return None

def save_quiz(q, course_id, course_name):
