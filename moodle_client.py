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

        if isinstance(data, dict) and "exception" in data:
            raise ValueError(
                f"Moodle API error [{wsfunction}]: {data.get('message', 'unknown')}"
            )
        return data

    def authenticate(self):
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
        site_info = self._api("core_webservice_get_site_info")
        self.user_id = site_info["userid"]
        logger.info("Authenticated as user_id=%s (%s)", self.user_id, site_info.get("fullname", ""))

    def get_courses(self):
        courses = self._api("core_enrol_get_users_courses", userid=self.user_id)
        logger.info("Found %d enrolled courses", len(courses))
        return courses

    def get_assignments(self, course_ids):
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
        if not course_ids:
            return []
        params = {f"courseids[{i}]": cid for i, cid in enumerate(course_ids)}
        data = self._api("mod_quiz_get_quizzes_by_courses", **params)
        quizzes = data.get("quizzes", [])
        logger.info("Found %d total quizzes", len(quizzes))
        return quizzes

    TRACKED_MODNAMES = {"resource", "folder", "url", "page"}

    def get_course_resources(self, course_id, course_name):
        """Fetch file/folder modules for a single course."""
        try:
            sections = self._api("core_course_get_contents", courseid=course_id)
        except ValueError as e:
            logger.warning("Could not fetch contents for course %d: %s", course_id, e)
            return []

        modules = []
        for section in sections:
            for mod in section.get("modules", []):
                if mod.get("modname") in self.TRACKED_MODNAMES:
                    mod["_course_id"] = course_id
                    mod["_course_name"] = course_name
                    modules.append(mod)
        return modules

    def get_announcement_discussions(self, courses):
        """Fetch discussions from each course's Announcements (news) forum."""
        if not courses:
            return []

        course_ids = [c["id"] for c in courses]
        course_map = {c["id"]: c["fullname"] for c in courses}

        params = {f"courseids[{i}]": cid for i, cid in enumerate(course_ids)}
        try:
            forums = self._api("mod_forum_get_forums_by_courses", **params)
        except ValueError as e:
            logger.warning("Could not fetch forums: %s", e)
            return []

        news_forums = [f for f in forums if f.get("type") == "news"]
        logger.info("Found %d announcement forum(s)", len(news_forums))

        discussions = []
        for forum in news_forums:
            forum_id = forum["id"]
            course_id = forum.get("course")
            course_name = course_map.get(course_id, "Unknown Course")
            try:
                data = self._api(
                    "mod_forum_get_forum_discussions",
                    forumid=forum_id,
                    perpage=20,
                )
                for d in data.get("discussions", []):
                    d["_forum_id"] = forum_id
                    d["_course_id"] = course_id
                    d["_course_name"] = course_name
                    discussions.append(d)
            except ValueError as e:
                logger.warning("Could not fetch discussions for forum %d: %s", forum_id, e)

        logger.info("Found %d total announcement(s)", len(discussions))
        return discussions

    def fetch_all(self):
        """
        Returns (assignments, quizzes, resources, discussions, course_names).
        """
        if not self.token:
            self.authenticate()

        try:
            courses = self.get_courses()
        except (requests.HTTPError, ValueError):
            logger.warning("API call failed, re-authenticating...")
            self.token = None
            self.authenticate()
            courses = self.get_courses()

        course_ids = [c["id"] for c in courses]
        course_names = {c["id"]: c["fullname"] for c in courses}

        assignments = self.get_assignments(course_ids)
        quizzes = self.get_quizzes(course_ids)

        resources = []
        for course in courses:
            resources.extend(self.get_course_resources(course["id"], course["fullname"]))
        logger.info("Found %d total resource/folder modules", len(resources))

        discussions = self.get_announcement_discussions(courses)

        return assignments, quizzes, resources, discussions, course_names
