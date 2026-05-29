# GiWiFi 校园网自动登录工具

## 项目信息
- **用途：** 校园网每天凌晨 3 点自动断线，本工具自动检测并重新登录
- **登录地址：** `http://172.27.253.230/gportal/web/login?wlanacname=SDZYY&wlanuserip=172.30.8.159`
- **技术栈：** Python 3.13.5 + PySide6 + requests
- **打包工具：** PyInstaller → `dist/GiWiFi.exe`

## 文件说明
| 文件 | 功能 |
|------|------|
| `main.py` | 主程序入口 |
| `tray_app.py` | PySide6 GUI 界面 + 系统托盘（液态玻璃 UI） |
| `login_worker.py` | HTTP 登录请求逻辑（含多种参数变体自动尝试） |
| `network_checker.py` | 后台线程每 30 秒检测网络连通性 |
| `config.py` | 账号密码配置管理（base64 编码存储） |
| `autostart.py` | Windows 注册表开机自启动 |
| `requirements.txt` | 依赖清单：PySide6, requests, pyinstaller |
| `FILEINFO.md` | 项目结构说明 |
| `main_window.ui` | Qt Designer 界面文件（备份） |

## 使用方法
1. 从 [Releases](https://github.com/Yuanxi01/GiWiFi-AutoLogin/releases) 下载 `GiWiFi.exe`
2. 双击运行，输入校园网账号密码，点击"保存配置"
3. 开启"开机自启动"可实现开机自动运行
4. 关闭窗口会最小化到系统托盘，双击图标恢复

## 重新打包
```bash
pip install -r requirements.txt
pyinstaller GiWiFi.spec --clean -y
```

## 开发日志
- **v1.0.1** (2025-05-28)：UI 全面升级，PySide6 + 液态玻璃设计风格
- **v1.0.0** (2025-05-27)：完成基础功能，GUI + 自动检测 + 登录 + 托盘 + 自启动
