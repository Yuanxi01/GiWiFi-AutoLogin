# GiWiFi 校园网自动登录工具

## 项目信息
- **用途：** 校园网每天凌晨 3 点自动断线，本工具自动检测并重新登录
- **登录地址：** `http://172.27.253.230/gportal/web/login?wlanacname=SDZYY&wlanuserip=172.30.8.159`
- **技术栈：** Python 3.13.5 + PyQt5 + requests
- **打包工具：** PyInstaller → `dist/GiWiFi.exe`

## 文件说明
| 文件 | 功能 |
|------|------|
| `main.py` | 主程序入口 |
| `tray_app.py` | PyQt5 GUI 界面 + 系统托盘 |
| `login_worker.py` | HTTP 登录请求逻辑（含多种参数变体自动尝试） |
| `network_checker.py` | 后台线程每 30 秒检测网络连通性 |
| `config.py` | 账号密码配置管理（base64 编码存储） |
| `autostart.py` | Windows 注册表开机自启动 |
| `requirements.txt` | 依赖清单：PyQt5, requests, pyinstaller |
| `dist/GiWiFi.exe` | 打包好的可执行文件 |

## 使用方法
1. 双击 `dist/GiWiFi.exe` 运行
2. 输入校园网账号密码，点击"保存配置"
3. 勾选"开机自启动"可实现开机自动运行
4. 关闭窗口会最小化到系统托盘，双击图标恢复

## 重新打包
```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --name GiWiFi main.py
```

## 开发日志
- 2025-05-27：完成基础功能，GUI + 自动检测 + 登录 + 托盘 + 自启动，已打包 exe
- **待验证：** 用户尚未在校园网环境实测登录是否成功，如失败需抓包确认 POST 参数格式
