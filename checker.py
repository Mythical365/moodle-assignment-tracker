"""
Moodle Assignment/Quiz Tracker

Usage:
    python3 checker.py          # runs forever
    python3 checker.py --once   # runs once and exits (GitHub Actions / testing)
"""

import sys
import time
import logging

from config import Config
from moodle_client import MoodleClient
from database import (
    init_db,
    check_assignment, save_assignment,
    check_quiz, save_quiz,
    check_resource, save_resource,
    check_forum_post, save_forum_post,
    get_items_due_soon, mark_reminded,
)
from notifier import (
    send_notification,
    send_reminders,
    send_test_notification,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("checker")

moodle = MoodleClient()


def is_future(ts):
    if not ts:
        return False
    return ts > int(time.time())


def run_check():
    logger.info("Starting Moodle check...")

    try:
        assignments, quizzes, resources, discussions, course_names = moodle.fetch_all()
    except Exception as e:
        logger.error("Failed to fetch from Moodle: %s", e)
        return

    new_assignments = []
    new_quizzes = []
    new_resources = []
    new_posts = []

    # Assignments
    for a in assignments:
        due = a.get("duedate")
        if due and not is_future(due):
            continue
        reason = check_assignment(a["id"], due)
        if reason:
            save_assignment(a)
            new_assignments.append((a, reason))
            logger.info("[%s] Assignment: %s (%s)", reason.upper(), a["name"], a["_course_name"])

    # Quizzes
    for q in quizzes:
        close_time = q.get("timeclose")
        course_id = q.get("course")
        course_name = course_names.get(course_id, "Unknown Course")
        q["_course_name"] = course_name
        if close_time and not is_future(close_time):
            continue
        reason = check_quiz(q["id"], close_time)
        if reason:
            save_quiz(q, course_id, course_name)
            new_quizzes.append((q, reason))
            logger.info("[%s] Quiz: %s (%s)", reason.upper(), q["name"], course_name)

    # Resources
    for r in resources:
        reason = check_resource(r["id"], r.get("timemodified"))
        if reason:
            save_resource(r)
            new_resources.append((r, reason))
            logger.info("[%s] %s: %s (%s)", reason.upper(), r["modname"], r["name"], r["_course_name"])

    # Forum announcements
    for d in discussions:
        if check_forum_post(d["id"]):
            save_forum_post(d)
            new_posts.append(d)
            logger.info("[NEW] Announcement: %s (%s)", d["name"], d["_course_name"])

    # Notify
    if new_assignments or new_quizzes or new_resources or new_posts:
        logger.info(
            "Found %d assignment(s), %d quiz(zes), %d resource(s), %d announcement(s)",
            len(new_assignments), len(new_quizzes), len(new_resources), len(new_posts),
        )
        try:
            send_notification(new_assignments, new_quizzes, new_resources, new_posts)
        except Exception as e:
            logger.error("Failed to send notification: %s", e)
    else:
        logger.info("No new items found.")

    # Reminders for upcoming deadlines
    _run_reminders()


def _run_reminders():
    try:
        due_assignments, due_quizzes = get_items_due_soon()
    except Exception as e:
        logger.error("Failed to query upcoming deadlines: %s", e)
        return

    if not due_assignments and not due_quizzes:
        return

    logger.info(
        "Reminders: %d assignment(s), %d quiz(zes) due within 24h",
        len(due_assignments), len(due_quizzes),
    )
    try:
        send_reminders(due_assignments, due_quizzes)
        for a in due_assignments:
            mark_reminded(a["id"])
        for q in due_quizzes:
            mark_reminded(q["id"])
    except Exception as e:
        logger.error("Failed to send reminders: %s", e)


def main():
    init_db()

    if "--once" in sys.argv:
        run_check()
        return

    logger.info(
        "Starting tracker loop — checking every %d minutes",
        Config.CHECK_INTERVAL_SECONDS // 60,
    )
    while True:
        run_check()
        time.sleep(Config.CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
