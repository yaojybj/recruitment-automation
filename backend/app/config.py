import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "recruitment.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

EMAIL_CHECK_INTERVAL_SECONDS = 60
FOLDER_WATCH_DIR = UPLOAD_DIR / "inbox"
FOLDER_WATCH_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR = UPLOAD_DIR / "archived"
ARCHIVE_DIR.mkdir(exist_ok=True)
