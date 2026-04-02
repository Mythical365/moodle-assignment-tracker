import os
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def is_seen(item_id: str, due_date: int) -> bool:
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/seen_items?id=eq.{item_id}&select=due_date",
        headers=HEADERS
    )
    data = res.json()
    if not data:
        return False  # never seen before
    return data[0]["due_date"] == due_date  # if due_date changed = reactivated

def mark_seen(item_id: str, item_type: str, due_date: int):
    requests.post(
        f"{SUPABASE_URL}/rest/v1/seen_items",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
        json={
            "id": item_id,
            "item_type": item_type,
            "due_date": due_date
        }
    )