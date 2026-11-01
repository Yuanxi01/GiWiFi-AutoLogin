# GiWiFi自动登录软件（山东中医药大学）v1.4.24

## 项目结构

```
校园网 - 1.4.0/
├── main.py                 # 程序入口
├── tray_app.py             # 主界面（自绘无边框窗口 + 托盘 + 业务编排）
├── config.py               # 配置读写（多账户 + 密码加密落盘）
├── secure_store.py         # 密码加密（Windows DPAPI / AES-256-GCM 兜底）
├── app_paths.py            # 用户数据目录（配置/日志放 %APPDATA%\GiWiFi）
├── login_worker.py         # 登录/下线/检测核心逻辑（GiWiFi 协议）
├── network_checker.py      # 网络状态轮询线程
├── autostart.py            # 开机自启动管理
├── logger.py               # 日志记录（LOG_FILE 绝对路径）
├── diagnose.py             # 断网四步诊断
├── dump_portal.py          # 认证页面抓取工具
├── themes/                 # 主题包
│   ├── __init__.py         #   导出 ThemeManager / 三个主题家族
│   ├── default.py          #   经典主题：晴空白 / 深夜蓝
│   ├── aurora.py           #   极光主题：Catppuccin Latte / Mocha
│   ├── innovate.py         #   蓝白创新（默认）：Material 按钮 + 流光描边
│   ├── liquid_glass.py     #   液态玻璃主题（Win11 毛玻璃）
│   └── theme_manager.py    #   主题切换持久化 + DWM backdrop
├── main_window.ui          # Qt Designer 界面文件（备份，已不使用）
├── requirements.txt        # Python 依赖
├── giwifi_config.json      # 运行时配置（密码为密文，已 .gitignore）
├── giwifi.log              # 运行日志
├── portal_page.html        # 认证页面样本
├── online_page.html        # 在线页面样本
├── logout_page.html        # 下线页面样本
├── _theme_preview/         # 开发用：离屏渲染的各主题截图与自测脚本（已 .gitignore）
├── README.md               # 项目说明
└── FILEINFO.md             # 本文件
```

## 依赖

```
PySide6>=6.5
requests>=2.28
pycryptodome>=3.15
psutil>=5.9
pyinstaller>=5.0
```

## 打包

```bash
pyinstaller --onefile --windowed --name GiWiFi main.py
```

输出: `dist/GiWiFi.exe`（约 49MB，无控制台窗口）

## 配置字段（giwifi_config.json）

| 字段 | 说明 |
|------|------|
| `username` / `password` | 当前使用的账号；password 为 DPAPI 密文（`dp1:` 前缀） |
| `accounts` | 多账户列表 `[{username, password}]`，password 同为密文 |
| `theme` | 主题家族：`default` / `aurora` / `liquid_glass` |
| `theme_mode` | 白天 `light` / 黑夜 `dark` / 跟随系统 `auto` |
| `scene_mode` | 使用场景：`auto` / `school` / `home` |
| `portal_url` | 认证页地址 |
| `check_interval` | 网络检测间隔（秒，默认 10） |

## UI 技术栈

- PySide6（Qt for Python），窗口与主要控件全部自绘
- 自定义 paintEvent 绘制窗口 / 卡片 / 强调条 / 极光光晕 / 玻璃散景
- 每个主题带一套 UI 结构参数：`UI_DEFAULT` / `UI_AURORA` / `UI_GLASS`
  （窗口圆角、卡片圆角、卡片间距、是否合并面板、装饰类型），主题差异不止配色
- 液态玻璃：`glass_backdrop.py` 抓屏 + 降采样模糊 + 按底图亮度自适应染色，
  两块卡片合并成一整块玻璃面板 + 刻槽分隔线
- 动效：`_tick_fx` 20fps 统一驱动（极光光晕漂移 + 状态点呼吸），
  `QPropertyAnimation` 驱动涟漪 / 水波纹 / 淡入淡出；窗口不可见时自动停画
- TrafficLight: macOS 红绿灯按钮
- StatusDot: 连接状态圆点（呼吸光晕 + 涟漪扩散）
- ToggleSwitch: 三套画法（经典凹槽 / 玻璃 / 极光 iOS 实心轨道）
- GlassButton: 主按钮（极光下为蓝紫横向渐变）+ 点击水波纹
- ShimmerButton: 蓝白创新的按钮（渐变 + 顶沿高光 + 扫光 + 波纹 + 按压位移）
- AccountMenuButton / EyeButton: 账号下拉箭头 / 密码可见性小眼睛
- 字体: Source Han Sans CN（思源黑体），缺失时回退 微软雅黑 → Segoe UI；
  最小字号 10pt（9pt 在 125% 缩放下会裁掉汉字字头）
- 配色: 经典 蓝白（#1D4ED8）/ 极光 Catppuccin（Latte / Mocha）/ 液态玻璃 半透明白
