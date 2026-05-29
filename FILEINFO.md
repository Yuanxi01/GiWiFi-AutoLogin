# GiWiFi自动登录软件（山东中医药大学）v1.0.1

## 项目结构

```
校园网 - 1.0.1/
├── main.py                 # 程序入口
├── tray_app.py             # 主界面（液态玻璃UI）
├── config.py               # 配置读写（JSON + Base64密码）
├── login_worker.py         # 登录/下线/检测核心逻辑
├── network_checker.py      # 网络状态轮询线程
├── autostart.py            # 开机自启动管理
├── logger.py               # 日志记录
├── dump_portal.py          # 认证页面抓取工具
├── main_window.ui          # Qt Designer 界面文件（备份，已不使用）
├── GiWiFi.spec             # PyInstaller 打包配置
├── requirements.txt        # Python 依赖
├── giwifi_config.json      # 运行时配置文件
├── giwifi.log              # 运行日志
├── portal_page.html        # 认证页面样本
├── online_page.html        # 在线页面样本
├── logout_page.html        # 下线页面样本
├── README.md               # 项目说明
└── FILEINFO.md             # 本文件
```

## 依赖

```
PySide6>=6.5
requests>=2.28
pycryptodome>=3.15
pyinstaller>=5.0
```

## 打包

```bash
pyinstaller GiWiFi.spec --clean -y
```

输出: `dist/GiWiFi.exe`（约 49MB，无控制台窗口）

## UI 技术栈

- PySide6（Qt for Python）
- 自定义 paintEvent 绘制液态玻璃效果
- TrafficLight: macOS 红绿灯按钮（自定义绘制）
- ToggleSwitch: iOS 风格滑动开关
- GlassButton: 液态玻璃按钮（发光 hover + 回弹 press）
- 字体: Source Han Sans CN（思源黑体 CN）
- 配色: 蓝白渐变 (#E8F4FD → #FFFFFF)
