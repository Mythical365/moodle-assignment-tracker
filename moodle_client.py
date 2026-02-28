import logging
import requests
from config import Config

logger = logging.getLogger(__name__)


class MoodleClient:
    def __init__(self):
        self.base_url = Config.MOODLE_URL.rstrip("/")
        self.token = None
        self.user_id = None
        self.session = requests.Session()
        self.session.timeout = 30

    def _api(self, wsfunction, **params):
        """Make an authenticated Moodle REST API call."""
        url = f"{self.base_url}/webservice/rest/server.php"
        payload = {
            "wstoken": self.token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **params,
        }
        resp = self.session.post(url, data=payload)
        resp.raise_for_status()
        data = resp.json()

        # Moodle returns 200 OK with {"exception": ..., "message": ...} on errors
        if isinstance(data, dict) and "exception" in data:
            raise ValueError(
                f"Moodle API error [{wsfunction}]: {data.get('message', 'unknown')}"
            )
        return data

    def authenticate(self):
        """Get a token from Moodle using saved credentials. Called automatically."""
        logger.info("Authenticating with Moodle at %s ...", self.base_url)
        resp = self.session.post(
            f"{self.base_url}/login/token.php",
            data={
                "username": Config.MOODLE_USERNAME,
                "password": Config.MOODLE_PASSWORD,
                "service": "moodle_mobile_app",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if "token" not in data:
            raise ValueError(f"Moodle auth failed: {data.get('error', data)}")

        self.token = data["token"]

        # Get our own user ID
        site_info = self._api("core_webservice_get_site_info")
        self.user_id = site_info["userid"]
        logger.info("Authenticated as user_id=%s (%s)", self.user_id, site_info.get("fullname", ""))

    def get_courses(self):
        """Get all courses the student is enrolled in."""
        courses = self._api("core_enrol_get_users_courses", userid=self.user_id)
        logger.info("Found %d enrolled courses", len(courses))
        return courses

    def get_assignments(self, course_ids):
        """Get all assignments from the given courses. Returns flat list."""
        if not course_ids:
            return []

        params = {f"courseids[{i}]": cid for i, cid in enumerate(course_ids)}
        data = self._api("mod_assign_get_assignments", **params)

        assignments = []
        for course in data.get("courses", []):
            for a in course.get("assignments", []):
                a["_course_id"] = course["id"]
                a["_course_name"] = course["fullname"]
                assignments.append(a)

        logger.info("Found %d total assignments", len(assignments))
        return assignments

    def get_quizzes(self, course_ids):
        """Get all quizzes from the given courses. Returns flat list."""
        if not course_ids:
            return []

        params = {f"courseids[{i}]": cid for i, cid in enumerate(course_ids)}
        data = self._api("mod_quiz_get_quizzes_by_courses", **params)

        quizzes = data.get("quizzes", [])
        logger.info("Found %d total quizzes", len(quizzes))
        return quizzes

    def fetch_all(self):
        """
        Main entry point: authenticate if needed, fetch everything.
        Returns (assignments, quizzes, course_names_dict).
        """
        if not self.token:
            self.authenticate()

        try:
            courses = self.get_courses()
        except (requests.HTTPError, ValueError):
            # Token might have expired — re-auth once
            logger.warning("API call failed, re-authenticating...")
            self.token = None
            self.authenticate()
            courses = self.get_courses()

        course_ids = [c["id"] for c in courses]
        course_names = {c["id"]: c["fullname"] for c in courses}

        assignments = self.get_assignments(course_ids)
        quizzes = self.get_quizzes(course_ids)

        return assignments, quizzes, course_names
