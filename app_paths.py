# -*- coding: utf-8 -*-
"""
app_paths.py —— 用户数据目录

配置和日志不再写在程序旁边（Program Files / 桌面 之类的位置经常没有写权限，
而且会把文件夹弄乱），统一放到 Windows 的用户数据目录：

    %APPDATA%\\GiWiFi\\giwifi_config.json
    %APPDATA%\\GiWiFi\\giwifi.log

老版本写在程序目录里的文件，第一次运行时会自动复制过来（不删除原文件）。
"""
import os
import shutil
import sys

APP_FOLDER = "GiWiFi"


def user_data_dir() -> str:
    """用户数据目录（不存在则创建）"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_FOLDER)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        # 极端情况下退回到用户主目录
        path = os.path.expanduser("~")
    return path


DATA_DIR = user_data_dir()


def data_path(name: str) -> str:
    """用户数据目录下的某个文件"""
    return os.path.join(DATA_DIR, name)


def legacy_path(name: str) -> str:
    """老版本的存放位置：exe 所在目录（源码运行时是项目目录）"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def migrate(name: str) -> str:
    """
    返回新位置的路径；若新位置还没有而老位置有，就先复制过去。
    这样升级后账号、密码、日志都还在，不会"一升级就空白"。
    """
    new = data_path(name)
    try:
        if not os.path.exists(new):
            old = legacy_path(name)
            if os.path.exists(old):
                shutil.copy2(old, new)
    except Exception:
        pass
    return new
