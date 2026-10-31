import os
import sys
from datetime import datetime

from app_paths import migrate

# 日志同样放到用户数据目录
LOG_FILE = migrate("giwifi.log")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
