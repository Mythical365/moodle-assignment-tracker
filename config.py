import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Moodle
    MOODLE_URL = "https://e-learning.msa.edu.eg"
    MOODLE_USERNAME = os.environ["MOODLE_USERNAME"]  # student ID
    MOODLE_PASSWORD = os.environ["MOODLE_PASSWORD"]

    # Discord
    DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

    # App
    CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "1800"))  # 30 min
    DATABASE_PATH = os.getenv("DATABASE_PATH", "tracker.db")
