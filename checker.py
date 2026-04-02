"""
Moodle Assignment/Quiz Tracker
Runs in an infinite loop — checks Moodle every 30 minutes and emails you
when new assignments or quizzes appear.

Usage:
    python3 checker.py          # runs forever (for Railway deployment)
    python3 checker.py --once   # runs once and exits (for testing)
"""

import os
import sys
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from config import Config
from moodle_client import MoodleClient
from database import (
    init_db,
    check_assignment,
    save_assignment,
    check_quiz,
    save_quiz
)
from notifier import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("checker")

moodle = MoodleClient()


def is_future(ts):
    """Return True if timestamp is in the future"""
    if not ts:
        return False
    return ts > int(time.time())


def run_check():
    logger.info("Starting Moodle check...")

    try:
        assignments, quizzes, course_names = moodle.fetch_all()
    except Exception as e:
        logger.error("Failed to fetch from Moodle: %s", e)
        return

    new_assignments = []
    new_quizzes = []

    # Assignments
    for a in assignments:
        due = a.get("duedate")

        if due and not is_future(due):
            continue

        reason = check_assignment(a["id"], due)

        if reason:
            save_assignment(a)
            new_assignments.append((a, reason))
            logger.info(
                "[%s] Assignment: %s (%s)",
                reason.upper(),
                a["name"],
                a["_course_name"],
            )

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
            logger.info(
                "[%s] Quiz: %s (%s)",
                reason.upper(),
                q["name"],
                course_name,
            )

    if new_assignments or new_quizzes:
        logger.info(
            "Sending notification: %d assignments, %d quizzes",
            len(new_assignments),
            len(new_quizzes),
        )

        try:
            send_notification(new_assignments, new_quizzes)
        except Exception as e:
            logger.error("Email failed: %s", e)
    else:
        logger.info("No new items found.")


def start_health_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *args):
            return

    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True
    )
    thread.start()

    logger.info("Health server running on port %s", port)


def main():
    init_db()

    if "--once" in sys.argv:
        run_check()
        return

    start_health_server()

    logger.info(
        "Running Moodle tracker every %d minutes",
        Config.CHECK_INTERVAL_SECONDS // 60
    )

    while True:
        run_check()
        time.sleep(Config.CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
