def _chunk(items, size=25):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def send_notification(new_assignments, new_quizzes, new_resources=None, new_posts=None):
    new_resources = new_resources or []
    new_posts = new_posts or []

    if not new_assignments and not new_quizzes and not new_resources and not new_posts:
        return

    embeds = []

    # Discord allows a maximum of 25 fields per embed.
    for chunk in _chunk(new_posts):
        fields = []
        for d in chunk:
            fields.append({
                "name": f"📢 {d['name']}",
                "value": (
                    f"**Course:** {d.get('_course_name', 'Unknown')}\n"
                    f"**Posted by:** {d.get('userfullname', 'Unknown')}"
                ),
                "inline": False,
            })

        embeds.append({
            "title": f"📣 New Announcement(s)",
            "color": 0x9B59B6,
            "fields": fields,
        })

    for chunk in _chunk(new_resources):
        fields = []
        for r, reason in chunk:
            icon = _MOD_ICON.get(r["modname"], "📎")
            tag = " 🔄 UPDATED" if reason == "updated" else ""

            fields.append({
                "name": f"{icon} {r['name']}{tag}",
                "value": f"**Course:** {r.get('_course_name', 'Unknown')}",
                "inline": False,
            })

        embeds.append({
            "title": "📂 New File(s) Uploaded",
            "color": 0x2ECC71,
            "fields": fields,
        })

    for chunk in _chunk(new_assignments):
        fields = []
        for a, reason in chunk:
            due = _format_date(a.get("duedate"))
            days = _days_until(a.get("duedate"))
            tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""

            fields.append({
                "name": f"📝 {a['name']}{tag}",
                "value": (
                    f"**Course:** {a.get('_course_name', 'Unknown')}\n"
                    f"**Due:** {due} {days}"
                ),
                "inline": False,
            })

        embeds.append({
            "title": "📚 New Assignment(s)",
            "color": 0xE74C3C,
            "fields": fields,
        })

    for chunk in _chunk(new_quizzes):
        fields = []
        for q, reason in chunk:
            closes = _format_date(q.get("timeclose"))
            days = _days_until(q.get("timeclose"))
            tag = " 🔄 REACTIVATED" if reason == "reactivated" else ""

            fields.append({
                "name": f"📋 {q['name']}{tag}",
                "value": (
                    f"**Course:** {q.get('_course_name', 'Unknown')}\n"
                    f"**Closes:** {closes} {days}"
                ),
                "inline": False,
            })

        embeds.append({
            "title": "📋 New Quiz(zes)",
            "color": 0xF39C12,
            "fields": fields,
        })

    total = (
        len(new_assignments)
        + len(new_quizzes)
        + len(new_resources)
        + len(new_posts)
    )

    # Discord allows at most 10 embeds per webhook message.
    # Send multiple webhook messages if necessary.
    for embed_chunk in _chunk(embeds, 10):
        _post_webhook({
            "content": (
                f"🚨 **{total} new item"
                f"{'s' if total != 1 else ''} found on Moodle!**"
            ),
            "embeds": embed_chunk,
        })

    logger.info("Discord notification sent: %d items", total)
