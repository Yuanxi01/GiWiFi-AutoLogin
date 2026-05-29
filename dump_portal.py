"""抓取 GiWiFi 认证页面完整 HTML，用于分析登录接口"""
import requests

PORTAL_URL = "http://172.27.253.230/gportal/web/login?wlanacname=SDZYY&wlanuserip=172.30.8.159"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

try:
    resp = requests.get(PORTAL_URL, headers=headers, timeout=10)
    with open("portal_page.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"已保存到 portal_page.html，长度: {len(resp.text)} 字节")
except Exception as e:
    print(f"错误: {e}")

input("按回车退出...")
