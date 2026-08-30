import re
import time
import json
import base64
import traceback
import requests
from urllib.parse import urlparse, urlencode, parse_qs

from logger import log

AES_KEY = b"1234567887654321"

# 全局 session，保持登录 cookies
_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def check_online(timeout: int = 5) -> tuple[bool, str | None]:
    """检测网络是否连通，返回 (是否在线, portal重定向URL)"""
    try:
        resp = requests.get("http://www.baidu.com", timeout=timeout, allow_redirects=False)
        log(f"检测网络: HTTP {resp.status_code}")
        if resp.status_code == 200:
            return True, None
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            log(f"重定向到: {location}")
            if "172.27.253.230" in location or "gportal" in location:
                return False, location
            return True, None
        return False, None
    except requests.RequestException as e:
        log(f"检测网络异常: {e}")
        return False, None


def _parse_form_fields(html: str) -> dict[str, str]:
    """从 HTML 中提取所有 input hidden 字段"""
    fields = {}
    for tag_match in re.finditer(r'<input\b[^>]*>', html, re.IGNORECASE):
        tag = tag_match.group(0)
        if not re.search(r'type\s*=\s*["\']hidden["\']', tag, re.IGNORECASE):
            continue
        name_m = re.search(r'name\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
        value_m = re.search(r'value\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if name_m:
            fields[name_m.group(1)] = value_m.group(1) if value_m else ""
    return fields


def _aes_encrypt(plaintext: str, iv: str) -> str:
    """AES-CBC 加密（ZeroPadding），返回 base64 字符串"""
    from Crypto.Cipher import AES
    data = plaintext.encode("utf-8")
    block_size = AES.block_size
    remainder = len(data) % block_size
    if remainder != 0:
        data += b'\x00' * (block_size - remainder)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv.encode("utf-8"))
    encrypted = cipher.encrypt(data)
    return base64.b64encode(encrypted).decode("utf-8")


def _parse_logout_url(data_str: str, base_url: str) -> str | None:
    """从登录响应的 data 字段解析出完整下线 URL"""
    if not data_str:
        return None
    if data_str.startswith("logout"):
        return f"{base_url}/gportal/web/{data_str}"
    return None


def get_online_duration(logout_url: str) -> str:
    """从下线 URL 中提取 lo 参数计算在线时长"""
    if not logout_url:
        return "未知"
    try:
        parsed = urlparse(logout_url)
        params = parse_qs(parsed.query)
        lo = int(params.get("lo", ["0"])[0])
        now = int(time.time())
        duration = max(0, now - lo)
        h = duration // 3600
        m = (duration % 3600) // 60
        s = duration % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except (ValueError, TypeError):
        return "未知"


def login_giwifi(username: str, password: str, portal_url: str) -> tuple[bool, str, str | None]:
    """登录，返回 (成功, 消息, 下线URL)"""
    if not username or not password:
        return False, "账号或密码为空", None

    try:
        log(f"开始登录, portal_url={portal_url}")
        parsed = urlparse(portal_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        log("步骤1: 获取认证页面...")
        resp = _session.get(portal_url, timeout=10)
        log(f"认证页面响应: HTTP {resp.status_code}, cookies={dict(_session.cookies)}")

        if resp.status_code != 200:
            return False, f"获取认证页面失败: HTTP {resp.status_code}", None

        fields = _parse_form_fields(resp.text)
        log(f"步骤2: 解析隐藏字段: {list(fields.keys())}")

        if not fields or "iv" not in fields:
            return False, "未找到登录表单字段", None

        fields["user_account"] = username
        fields["user_password"] = password
        log(f"步骤3: 填入账号密码，总字段数={len(fields)}")

        iv = fields["iv"]
        form_data_str = urlencode(fields)
        encrypted_data = _aes_encrypt(form_data_str, iv)
        log(f"步骤4: AES 加密完成, iv={iv}")

        login_url = f"{base_url}/gportal/Web/loginAction"
        post_data = {"data": encrypted_data, "iv": iv}

        log(f"步骤5: POST 到 {login_url}")
        resp = _session.post(login_url, data=post_data, timeout=10)
        log(f"响应: HTTP {resp.status_code}, {resp.text[:300]}")

        result = resp.json()
        status = result.get("status")
        info = result.get("info", "")
        data = result.get("data", "")
        log(f"步骤6: status={status}, info={info}, data={data[:100]}")

        if status == 1:
            logout_url = _parse_logout_url(data, base_url)
            return True, "登录成功", logout_url
        else:
            return False, f"登录失败: {info}", None

    except Exception as e:
        log(f"登录异常: {e}\n{traceback.format_exc()}")
        return False, f"错误: {e}", None


def logout_giwifi(logout_url: str) -> tuple[bool, str]:
    """直接用 si 参数 POST 下线（无需加密）"""
    try:
        log(f"开始下线, url={logout_url}")
        parsed = urlparse(logout_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        params = parse_qs(parsed.query)
        si = params.get("si", [""])[0]

        if not si:
            return False, "下线 URL 中缺少 si 参数"

        logout_endpoint = f"{base_url}/gportal/Web/logoutAction"
        post_data = {"si": si}
        log(f"POST 下线到 {logout_endpoint}, si={si}")

        resp = _session.post(logout_endpoint, data=post_data, timeout=10)
        log(f"下线响应: {resp.status_code}, {resp.text[:300]}")

        try:
            result = resp.json()
            status = result.get("status")
            info = result.get("info", "")
            if status == 1:
                return True, f"下线成功: {info}"
            else:
                return False, f"下线失败: {info}"
        except Exception:
            return False, f"响应格式异常: {resp.text[:200]}"

    except Exception as e:
        log(f"下线异常: {e}\n{traceback.format_exc()}")
        return False, f"错误: {e}"
