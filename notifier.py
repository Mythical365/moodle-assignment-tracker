import time
import logging
import requests
from datetime import datetime, timezone
from config import Config

logger = logging.getLogger(__name__)


def _format_date(ts):
    """Convert unix timestamp to human readable string."""
    if not ts:
        return "No deadline set"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return dt.strftime("%A, %d %b %Y at %I:%M %p")


def _days_until(ts):
    """Return a string like '2 days away' or 'due TODAY'."""
    if not ts:
        return ""
    days = (ts - int(time.time())) / 86400
    if days < 0:
        return "(overdue)"
    if days < 1:
        return "⚠️ **due TODAY**"
    if days < 2:
        return "⚠️ **due TOMORROW**"
    return f"({int(days)} days away)"


def _build_discord_embeds(new_assignments, new_quizzes):
    """Build Discord embed objects for the webhook."""
    embeds = []

    if new_assignments:
        fields = []
        for a, reason in new_assignments:
            due = _format_date(a.get("duedate"))
            days = _days_until(a.get("duedate"))
            tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""
            course = a.get("_course_name", "Unknown")

            fields.append({
                "name": f"📝 {a['name']}{tag}",
                "value": f"**Course:** {course}\n**Due:** {due} {days}",
                "inline": False,
            })

        embeds.append({
            "title": f"📚 {len(new_assignments)} New Assignment(s)",
            "color": 0xE74C3C,  # red
            "fields": fields,
        })

    if new_quizzes:
        fields = []
        for q, reason in new_quizzes:
            closes = _format_date(q.get("timeclose"))
            days = _days_until(q.get("timeclose"))
            tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""
            course = q.get("_course_name", "Unknown")

            fields.append({
                "name": f"📋 {q['name']}{tag}",
                "value": f"**Course:** {course}\n**Closes:** {closes} {days}",
                "inline": False,
            })

        embeds.append({
            "title": f"📋 {len(new_quizzes)} New Quiz(zes)",
            "color": 0xF39C12,  # orange
            "fields": fields,
        })

    return embeds


def send_notification(new_assignments, new_quizzes):
    """
    Send a Discord webhook notification about new items.
    new_assignments: list of (assignment_dict, reason) tuples
    new_quizzes: list of (quiz_dict, reason) tuples
    """
    if not new_assignments and not new_quizzes:
        return

    total = len(new_assignments) + len(new_quizzes)
    embeds = _build_discord_embeds(new_assignments, new_quizzes)

    payload = {
        "content": f"🚨 **{total} new item{'s' if total != 1 else ''} found on Moodle!**",
        "embeds": embeds,
    }

    resp = requests.post(Config.DISCORD_WEBHOOK_URL, json=payload, timeout=15)

    if resp.status_code == 204:
        logger.info("Discord notification sent: %d items", total)
    else:
        logger.error("Discord webhook failed (%d): %s", resp.status_code, resp.text)
        resp.raise_for_status()
