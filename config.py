import json
import os
import sys

from secure_store import encrypt_secret, decrypt_secret

from app_paths import migrate

# 配置放到 %APPDATA%\GiWiFi\ 下，不再写在程序目录里
# （migrate 会把老版本放在程序目录的配置自动搬过来）
CONFIG_FILE = migrate("giwifi_config.json")

DEFAULT_CONFIG = {
    # 默认主题：蓝白创新（蓝白配色 + Material 按钮）
    "theme": "innovate",
    "username": "",
    "password": "",
    "portal_url": "http://172.27.253.230/gportal/web/login",
    "wlanacname": "SDZYY",
    "check_interval": 10,
    "autostart": False,
    # 多账户：[{"username": "...", "password": "明文（仅内存态）"}]
    # 落盘时 password 统一走 DPAPI 加密
    "accounts": [],
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = DEFAULT_CONFIG.copy()
    config.update(data)

    # 当前账号密码（旧配置是裸 base64，新配置是 DPAPI 密文，都能解开）
    config["password"] = decrypt_secret(config.get("password", ""))

    # 已保存的账户列表：逐个解密，顺手丢掉脏数据
    accounts = []
    for item in config.get("accounts") or []:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username", "")).strip()
        if not username:
            continue
        accounts.append({
            "username": username,
            "password": decrypt_secret(item.get("password", "")),
        })

    # 老配置迁移：只有一个账号时自动补进账户列表
    if not accounts and config.get("username"):
        accounts = [{
            "username": config["username"],
            "password": config["password"],
        }]
    config["accounts"] = accounts

    # 一次性迁移：默认主题从「经典」改为「蓝白创新」。
    # 只在没有迁移标记时执行一次，之后用户手动选「经典」就不会再被改回来。
    if not config.get("theme_migrated_v2"):
        config["theme"] = "innovate"
        config["theme_migrated_v2"] = True
        try:
            save_config(config)
        except Exception:
            pass
    return config


def save_config(config: dict):
    data = config.copy()

    # 落盘前加密（DPAPI 绑定当前 Windows 用户 + 当前机器）
    data["password"] = encrypt_secret(data.get("password", ""))

    accounts = []
    for item in config.get("accounts") or []:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username", "")).strip()
        if not username:
            continue
        accounts.append({
            "username": username,
            "password": encrypt_secret(item.get("password", "")),
        })
    data["accounts"] = accounts

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
