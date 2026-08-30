"""断网诊断：依次检查 物理连接 → 网关 → 认证系统 → 外网，定位掉线原因"""
import re
import socket
import subprocess

import psutil
import requests

from logger import log


def _default_gateway():
    """从 Windows 路由表取默认网关 IPv4"""
    try:
        out = subprocess.run(
            ["route", "print", "-4", "0.0.0.0"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                gw = parts[2]
                if gw and gw != "On-link" and re.match(r"\d+\.\d+\.\d+\.\d+", gw):
                    return gw
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0" and parts[2] == "On-link":
                if re.match(r"\d+\.\d+\.\d+\.\d+", parts[3]):
                    return parts[3]
    except Exception as e:
        log(f"诊断: 读取网关失败 {e}")
    return None


def _ping(host: str) -> bool:
    try:
        r = subprocess.run(
            ["ping", "-n", "1", "-w", "2000", host],
            capture_output=True, text=True, timeout=6,
        )
        return r.returncode == 0
    except Exception:
        return False


def _has_alive_nic() -> bool:
    """是否有已连接且拿到有效 IPv4 的非回环网卡"""
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, st in stats.items():
            if not st.isup or "Loopback" in name or "回环" in name:
                continue
            for a in addrs.get(name, []):
                if a.family == socket.AF_INET and a.address:
                    if not a.address.startswith("169.254"):  # 排除 DHCP 失败的自动私有地址
                        return True
    except Exception as e:
        log(f"诊断: 读取网卡失败 {e}")
    return False


def run_diagnosis(portal_url: str = "") -> tuple[list, str]:
    """执行四步诊断，返回 (报告行列表, 结论)。任何一步都不会抛异常。"""
    steps = []

    # 1. 物理连接
    nic_ok = _has_alive_nic()
    steps.append(("物理连接（网线 / Wi-Fi）", nic_ok,
                  "没有检测到已连接的网卡，请检查网线是否插好、Wi-Fi 是否连接校园网"))

    # 2. 网关
    gw = _default_gateway()
    gw_ok = bool(gw) and _ping(gw)
    steps.append((f"网关连通（{gw or '未获取到'}）", gw_ok,
                  "已连上校园网但网关不通：建议忘记网络后重连 Wi-Fi，或联系宿舍楼网管"))

    # 3. 认证系统
    portal = portal_url or "http://172.27.253.230/gportal/web/login"
    portal_ok = False
    try:
        requests.get(portal, timeout=6)
        portal_ok = True  # 任意 HTTP 响应都算可达（含 302/403）
    except Exception:
        portal_ok = False
    steps.append(("校园网认证系统", portal_ok,
                  "认证系统不可达：多半是学校认证服务故障，稍等即可，不用反复尝试登录"))

    # 4. 外网
    net_ok = False
    try:
        r = requests.get("http://www.baidu.com", timeout=6, allow_redirects=False)
        net_ok = r.status_code in (200, 301, 302)
    except Exception:
        net_ok = False
    steps.append(("外网连通", net_ok,
                  "认证系统正常但外网不通：可能还没认证成功，请点「手动登录」；若已登录仍不通，是学校外网故障，等待恢复即可"))

    lines = []
    verdict = "当前网络一切正常，无需处理～"
    for name, ok, hint in steps:
        lines.append(f"{'✅' if ok else '❌'} {name}")
        if not ok:
            lines.append(f"    ↳ {hint}")
    if not all(ok for _, ok, _ in steps):
        first_bad = next((hint for _, ok, hint in steps if not ok), None)
        verdict = f"诊断结论：{first_bad}"
    lines.append("")
    lines.append(verdict)
    log("断网诊断完成: " + " | ".join(f"{n}={'OK' if ok else 'FAIL'}" for n, ok, _ in steps))
    return lines, verdict
