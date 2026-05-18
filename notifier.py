import time
import logging
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import Config

logger = logging.getLogger(__name__)


def _format_date(ts):
    if not ts:
        return "No deadline set"
    tz = ZoneInfo(Config.TIMEZONE)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
    return dt.strftime("%A, %d %b %Y at %I:%M %p")


def _days_until(ts):
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


_MOD_ICON = {"resource": "📄", "folder": "📁", "url": "🔗", "page": "📃"}


def _post_webhook(payload):
    resp = requests.post(Config.DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    if resp.status_code == 204:
        return
    logger.error("Discord webhook failed (%d): %s", resp.status_code, resp.text)
    resp.raise_for_status()


def send_notification(new_assignments, new_quizzes, new_resources=None, new_posts=None):
    new_resources = new_resources or []
    new_posts = new_posts or []
    if not new_assignments and not new_quizzes and not new_resources and not new_posts:
        return

    embeds = []

    if new_posts:
        fields = []
        for d in new_posts:
            fields.append({
                "name": f"📢 {d['name']}",
                "value": f"**Course:** {d.get('_course_name', 'Unknown')}\n**Posted by:** {d.get('userfullname', 'Unknown')}",
                "inline": False,
            })
        embeds.append({
            "title": f"📣 {len(new_posts)} New Announcement(s)",
            "color": 0x9B59B6,
            "fields": fields,
        })

    if new_resources:
        fields = []
        for r, reason in new_resources:
            icon = _MOD_ICON.get(r["modname"], "📎")
            tag = " 🔄 UPDATED" if reason == "updated" else ""
            fields.append({
                "name": f"{icon} {r['name']}{tag}",
                "value": f"**Course:** {r.get('_course_name', 'Unknown')}",
                "inline": False,
            })
        embeds.append({
            "title": f"📂 {len(new_resources)} New File(s) Uploaded",
            "color": 0x2ECC71,
            "fields": fields,
        })

    if new_assignments:
        fields = []
        for a, reason in new_assignments:
            due = _format_date(a.get("duedate"))
            days = _days_until(a.get("duedate"))
            tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""
            fields.append({
                "name": f"📝 {a['name']}{tag}",
                "value": f"**Course:** {a.get('_course_name', 'Unknown')}\n**Due:** {due} {days}",
                "inline": False,
            })
        embeds.append({
            "title": f"📚 {len(new_assignments)} New Assignment(s)",
            "color": 0xE74C3C,
            "fields": fields,
        })

    if new_quizzes:
        fields = []
        for q, reason in new_quizzes:
            closes = _format_date(q.get("timeclose"))
            days = _days_until(q.get("timeclose"))
            tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""
            fields.append({
                "name": f"📋 {q['name']}{tag}",
                "value": f"**Course:** {q.get('_course_name', 'Unknown')}\n**Closes:** {closes} {days}",
                "inline": False,
            })
        embeds.append({
            "title": f"📋 {len(new_quizzes)} New Quiz(zes)",
            "color": 0xF39C12,
            "fields": fields,
        })

    total = len(new_assignments) + len(new_quizzes) + len(new_resources) + len(new_posts)
    _post_webhook({
        "content": f"🚨 **{total} new item{'s' if total != 1 else ''} found on Moodle!**",
        "embeds": embeds,
    })
    logger.info("Discord notification sent: %d items", total)


def send_reminders(assignments, quizzes):
    """Reminder ping for items due within 24h. Uses Supabase row dicts."""
    if not assignments and not quizzes:
        return

    fields = []
    for a in assignments:
        due = _format_date(a["due_date"])
        days = _days_until(a["due_date"])
        fields.append({
            "name": f"📝 {a['name']}",
            "value": f"**Course:** {a['course_name']}\n**Due:** {due} {days}",
            "inline": False,
        })
    for q in quizzes:
        closes = _format_date(q["due_date"])
        days = _days_until(q["due_date"])
        fields.append({
            "name": f"📋 {q['name']}",
            "value": f"**Course:** {q['course_name']}\n**Closes:** {closes} {days}",
            "inline": False,
        })

    total = len(assignments) + len(quizzes)
    _post_webhook({
        "content": f"⏰ **Reminder: {total} deadline{'s' if total != 1 else ''} in less than 24 hours!**",
        "embeds": [{
            "title": "Upcoming Deadlines",
            "color": 0xF1C40F,
            "fields": fields,
        }],
    })
    logger.info("Reminder sent for %d item(s)", total)
