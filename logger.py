import os
import sys
from datetime import datetime

if getattr(sys, "frozen", False):
    LOG_DIR = os.path.dirname(sys.executable)
else:
    LOG_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(LOG_DIR, "giwifi.log")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
