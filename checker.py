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
from database import init_db, check_assignment, save_assignment, check_quiz, save_quiz
from notifier import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("checker")

# Single client instance — keeps the token between checks
moodle = MoodleClient()


def is_future(ts):
    """Return True if the timestamp is in the future (or not set)."""
    if not ts:
        return False
    return ts > int(time.time())


def run_check():
    """Fetch from Moodle, filter, compare with DB, notify if new items found."""
    logger.info("Starting Moodle check...")

    try:
        assignments, quizzes, course_names = moodle.fetch_all()
    except Exception as e:
        logger.error("Failed to fetch from Moodle: %s", e)
        return

    new_assignments = []  # list of (assignment, reason) tuples
    new_quizzes = []      # list of (quiz, reason) tuples

    # --- Filter and check assignments ---
    for a in assignments:
        due = a.get("duedate")

        # Skip assignments with past due dates (old semester leftovers)
        if due and not is_future(due):
            continue

        reason = check_assignment(a["id"], due)
        if reason:  # 'new' or 'reactivated'
            save_assignment(a)
            new_assignments.append((a, reason))
            logger.info(
                "  [%s] Assignment: %s (%s)", reason.upper(), a["name"], a["_course_name"]
            )

    # --- Filter and check quizzes ---
    for q in quizzes:
        close_time = q.get("timeclose")
        course_id = q.get("course")
        course_name = course_names.get(course_id, "Unknown Course")
        q["_course_name"] = course_name

        # Skip quizzes that have already closed
        if close_time and not is_future(close_time):
            continue

        reason = check_quiz(q["id"], close_time)
        if reason:
            save_quiz(q, course_id, course_name)
            new_quizzes.append((q, reason))
            logger.info(
                "  [%s] Quiz: %s (%s)", reason.upper(), q["name"], course_name
            )

    # --- Send email if anything new ---
    if new_assignments or new_quizzes:
        logger.info(
            "Found %d new assignment(s) and %d new quiz(zes) — sending email...",
            len(new_assignments),
            len(new_quizzes),
        )
        try:
            send_notification(new_assignments, new_quizzes)
        except Exception as e:
            logger.error("Failed to send email: %s", e)
    else:
        logger.info("No new items found.")


def main():
    init_db()

    once = "--once" in sys.argv

    if once:
        logger.info("Running single check (--once mode)")
        run_check()
        return

    # Start a tiny HTTP server so Railway knows we're alive
    _start_health_server()

    # Infinite loop for deployment (Railway, etc.)
    logger.info(
        "Starting tracker loop — checking every %d seconds (%d minutes)",
        Config.CHECK_INTERVAL_SECONDS,
        Config.CHECK_INTERVAL_SECONDS // 60,
    )

    while True:
        run_check()
        logger.info(
            "Sleeping %d minutes until next check...",
            Config.CHECK_INTERVAL_SECONDS // 60,
        )
        time.sleep(Config.CHECK_INTERVAL_SECONDS)


def _start_health_server():
    """Tiny HTTP server so Railway sees a listening port and doesn't mark us as crashed."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *args):
            pass  # silence request logs

    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health server listening on port %d", port)


if __name__ == "__main__":
    main()
