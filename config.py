import json
import base64
import os
import sys

if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(_APP_DIR, "giwifi_config.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "portal_url": "http://172.27.253.230/gportal/web/login",
    "wlanacname": "SDZYY",
    "check_interval": 10,
    "autostart": False,
}


def _encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def _decode(text: str) -> str:
    return base64.b64decode(text.encode("utf-8")).decode("utf-8")


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = DEFAULT_CONFIG.copy()
    config.update(data)
    if config.get("password"):
        try:
            config["password"] = _decode(config["password"])
        except Exception:
            pass
    return config


def save_config(config: dict):
    data = config.copy()
    if data.get("password"):
        data["password"] = _encode(data["password"])
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
