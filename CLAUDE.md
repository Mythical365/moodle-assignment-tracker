# Moodle Assignment/Quiz Tracker

## Project Overview
Automated Python script that monitors MSA University's Moodle portal (`e-learning.msa.edu.eg`) every 30 minutes and sends Discord notifications when new assignments or quizzes appear. Runs on a GitHub Actions cron (every 30 min, `checker.py --once`); `Procfile` is kept for optional Railway/loop mode.

## Architecture
- **No web framework** — pure Python script running in an infinite loop (`checker.py`)
- **Moodle REST API** via `moodle_mobile_app` web service for data fetching
- **Neon (serverless Postgres)** via `psycopg` (`DATABASE_URL`) for tracking seen items and detecting reactivated ones
- **Discord webhook** for notifications (replaced Gmail — App Passwords were unavailable)
- **Railway.app** for hosting (Procfile-based deployment)

## File Structure
- `config.py` — loads env vars (Moodle creds, Discord webhook URL, check interval)
- `moodle_client.py` — Moodle API client (auth, courses, assignments, quizzes). Token auto-retry on expiry.
- `database.py` — Neon/Postgres schema, seen-checking, reactivation detection via date comparison (single reused connection, auto-reconnect)
- `notifier.py` — builds Discord embed messages and sends via webhook
- `checker.py` — main entry point. Infinite loop with `--once` flag for testing
- `Procfile` — `worker: python3 checker.py` (Railway reads this)
- `.env` — secrets (not committed). `.env.example` has the template

## Key Design Decisions
- **Smart filtering**: Only notifies about items with future deadlines. Old semester leftovers are ignored.
- **Reactivation detection**: If a professor changes an old item's due date to a future date, it re-notifies (DB stores last-seen due_date and compares on each check).
- **Deduplication**: `INSERT OR IGNORE` / `ON CONFLICT` on Moodle's native IDs prevents duplicate notifications.
- **No Flask/web dashboard**: User only wanted Discord notifications, no UI needed.

## Moodle API Details
- Base URL: `https://e-learning.msa.edu.eg`
- Auth: POST to `/login/token.php` with service=`moodle_mobile_app` → returns token
- Key functions used:
  - `core_webservice_get_site_info` → user ID
  - `core_enrol_get_users_courses` → enrolled courses
  - `mod_assign_get_assignments` → assignments with `duedate` (unix timestamp)
  - `mod_quiz_get_quizzes_by_courses` → quizzes with `timeopen`/`timeclose`
- Course IDs are passed as `courseids[0]=X&courseids[1]=Y` format
- Moodle returns errors as 200 OK with `{"exception": ..., "message": ...}` — handled in `_api()`

## Deployment
- **Host**: Railway.app (free tier, $5 credit/month — script uses ~$0.50/month)
- **Env vars**: Set in Railway dashboard (MOODLE_URL, MOODLE_USERNAME, MOODLE_PASSWORD, DISCORD_WEBHOOK_URL)
- **GitHub repo**: Private at `Mythical365/moodle-assignment-tracker`
- Railway auto-deploys on push to `main`

## Testing
- `python3 checker.py --once` — single check, good for testing
- `python3 checker.py` — infinite loop mode (production)
- Second run should always print "No new items found" (dedup working)

## Current Limitations / Known Issues
- **Quizzes**: Currently 0 quizzes found — professors may not have any active yet. The quiz fetching code is ready and will work when they appear.
- **No deadline items**: Items with `duedate=0` (like "Total Tasks Grades") are treated as new on first run but have no useful deadline info in the notification.
- **Railway disk**: SQLite file persists between checks but is lost on redeploy. First check after redeploy re-scans everything — smart filtering prevents false notifications for old items, but items already seen before the redeploy will be re-notified if they still have future dates.

## Future Improvement Ideas
- **Track course resources/files too**: Use `core_course_get_contents` to detect new uploaded files (PDFs, slides, etc.) — not just assignments/quizzes
- **Forum post tracking**: Detect new forum posts/announcements via `mod_forum_get_forum_discussions`
- **Due date reminders**: Send a reminder 24h and 1h before a deadline (not just when the item first appears)
- **Grade notifications**: Use `gradereport_user_get_grade_items` to notify when a grade is posted
- **Multiple notification channels**: Support both Discord + Telegram simultaneously
- **Persist DB across redeploys**: Use Railway volumes or switch to a hosted DB (Turso free tier) so seen-items survive redeploys
- **Web dashboard**: Simple page showing all upcoming deadlines (was declined but could be added later)
- **Per-course filtering**: Allow ignoring certain courses (e.g., old ones that haven't been unenrolled)
- **Smarter no-deadline filtering**: Skip items with no deadline that are clearly grade placeholders (like "Total Tasks Grades")
