import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("SAGE_DB", "sage.db")
TIMEZONE = os.getenv("SAGE_TZ", "Asia/Kolkata")
USER_NAME = os.getenv("SAGE_USER_NAME", "Alex S.")

# ---- scheduling ----
DEFAULT_SESSION_MIN = 45
DEFAULT_BREAK_MIN = 10
MIN_BLOCK_MIN = 20
MAX_SESSION_MIN = 180
MAX_DAYS_AHEAD = 120
REVISION_UNIT_MIN = 30
REMIND_BEFORE_MIN = 10

WEIGHTS = {
    "urgency": 0.35,
    "understanding": 0.30,
    "difficulty": 0.15,
    "unfinished": 0.10,
    "revision": 0.10,
}

# ---- course goals: label shown in the UI -> short label + effort multiplier ----
GOALS = {
    "A (4.0 GPA · Mastery)": {"short": "4.0 GPA", "factor": 1.25},
    "B (3.0 GPA · Strong)": {"short": "3.0 GPA", "factor": 1.0},
    "Pass (Core concepts)": {"short": "Pass", "factor": 0.75},
}
DEFAULT_GOAL = "A (4.0 GPA · Mastery)"

# ---- default weekly study windows ----
DEFAULT_WINDOWS = {"weekday": ("19:00", "21:00"), "weekend": ("10:00", "14:00")}

# ---- AI providers ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
CLOUD_TIMEOUT_S = 15
CLOUD_RETRIES = 2
LOCAL_TIMEOUT_S = 60

# ---- Google Calendar ----
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_TOKEN_FILE = "token.json"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]