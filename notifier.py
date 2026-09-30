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


_MOD_ICON = {
    "resource": "📄",
    "folder": "📁",
    "url": "🔗",
    "page": "📃",
}


def _post_webhook(payload):
    resp = requests.post(
        Config.DISCORD_WEBHOOK_URL,
        json=payload,
        timeout=15,
    )

    if resp.status_code == 204:
        return

    logger.error(
        "Discord webhook failed (%d): %s",
        resp.status_code,
        resp.text,
    )
    resp.raise_for_status()


def _chunk(items, size=25):
    """Split a list into chunks of at most `size` items."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _build_embeds(items, title, color):
    """
    Build Discord embeds with no more than 25 fields each.

    Discord also limits the total text inside one embed, so we keep
    the field count conservative.
    """
    embeds = []

    for chunk in _chunk(items, 25):
        fields = []

        for item in chunk:
            fields.append(item)

        embeds.append({
            "title": title,
            "color": color,
            "fields": fields,
        })

    return embeds


def send_notification(
    new_assignments,
    new_quizzes,
    new_resources=None,
    new_posts=None,
):
    new_resources = new_resources or []
    new_posts = new_posts or []

    if (
        not new_assignments
        and not new_quizzes
        and not new_resources
        and not new_posts
    ):
        return

    embeds = []

    # Announcements
    announcement_fields = []

    for d in new_posts:
        announcement_fields.append({
            "name": f"📢 {d['name']}",
            "value": (
                f"**Course:** {d.get('_course_name', 'Unknown')}\n"
                f"**Posted by:** {d.get('userfullname', 'Unknown')}"
            ),
            "inline": False,
        })

    if announcement_fields:
        embeds.extend(
            _build_embeds(
                announcement_fields,
                "📣 New Announcement(s)",
                0x9B59B6,
            )
        )

    # Resources
    resource_fields = []

    for r, reason in new_resources:
        icon = _MOD_ICON.get(r["modname"], "📎")
        tag = " 🔄 UPDATED" if reason == "updated" else ""

        resource_fields.append({
            "name": f"{icon} {r['name']}{tag}",
            "value": (
                f"**Course:** "
                f"{r.get('_course_name', 'Unknown')}"
            ),
            "inline": False,
        })

    if resource_fields:
        embeds.extend(
            _build_embeds(
                resource_fields,
                "📂 New File(s) Uploaded",
                0x2ECC71,
            )
        )

    # Assignments
    assignment_fields = []

    for a, reason in new_assignments:
        due = _format_date(a.get("duedate"))
        days = _days_until(a.get("duedate"))
        tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""

        assignment_fields.append({
            "name": f"📝 {a['name']}{tag}",
            "value": (
                f"**Course:** "
                f"{a.get('_course_name', 'Unknown')}\n"
                f"**Due:** {due} {days}"
            ),
            "inline": False,
        })

    if assignment_fields:
        embeds.extend(
            _build_embeds(
                assignment_fields,
                "📚 New Assignment(s)",
                0xE74C3C,
            )
        )

    # Quizzes
    quiz_fields = []

    for q, reason in new_quizzes:
        closes = _format_date(q.get("timeclose"))
        days = _days_until(q.get("timeclose"))
        tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""

        quiz_fields.append({
            "name": f"📋 {q['name']}{tag}",
            "value": (
                f"**Course:** "
                f"{q.get('_course_name', 'Unknown')}\n"
                f"**Closes:** {closes} {days}"
            ),
            "inline": False,
        })

    if quiz_fields:
        embeds.extend(
            _build_embeds(
                quiz_fields,
                "📋 New Quiz(zes)",
                0xF39C12,
            )
        )

    total = (
        len(new_assignments)
        + len(new_quizzes)
        + len(new_resources)
        + len(new_posts)
    )

    # Discord allows at most 10 embeds in one webhook message.
    for embed_chunk in _chunk(embeds, 10):
        _post_webhook({
            "content": (
                f"🚨 **{total} new item"
                f"{'s' if total != 1 else ''} found on Moodle!**"
            ),
            "embeds": embed_chunk,
        })

    logger.info(
        "Discord notification sent: %d items",
        total,
    )


def send_reminders(assignments, quizzes):
    """Send reminders for assignments and quizzes due within 24 hours."""
    if not assignments and not quizzes:
        return

    fields = []

    for a in assignments:
        due = _format_date(a["due_date"])
        days = _days_until(a["due_date"])

        fields.append({
            "name": f"📝 {a['name']}",
            "value": (
                f"**Course:** {a['course_name']}\n"
                f"**Due:** {due} {days}"
            ),
            "inline": False,
        })

    for q in quizzes:
        closes = _format_date(q["due_date"])
        days = _days_until(q["due_date"])

        fields.append({
            "name": f"📋 {q['name']}",
            "value": (
                f"**Course:** {q['course_name']}\n"
                f"**Closes:** {closes} {days}"
            ),
            "inline": False,
        })

    total = len(assignments) + len(quizzes)

    # Split reminders too, just in case there are more than 25.
    embeds = _build_embeds(
        fields,
        "Upcoming Deadlines",
        0xF1C40F,
    )

    # Discord allows at most 10 embeds per webhook message.
    for embed_chunk in _chunk(embeds, 10):
        _post_webhook({
            "content": (
                f"⏰ **Reminder: {total} deadline"
                f"{'s' if total != 1 else ''} "
                f"in less than 24 hours!**"
            ),
            "embeds": embed_chunk,
        })

    logger.info(
        "Reminder sent for %d item(s)",
        total,
    )
