# -*- coding: utf-8 -*-
"""
secure_store.py —— 本地凭据加密（Windows DPAPI 优先，AES 兜底）

为什么不用 base64
-----------------
base64 只是编码，任何人拿到 giwifi_config.json 都能一眼还原出校园网密码。

加密方案
--------
1. 首选 **Windows DPAPI**（crypt32!CryptProtectData）
   密钥由系统托管，绑定「当前 Windows 用户 + 当前机器」，不落磁盘。
   换机器 / 换用户都解不开 —— 正好符合需求：配置文件被别人拷走也没用。
   另外用一段应用专属 entropy 做二次隔离，避免同机其它程序直接解开我们的密文。
2. 兜底（DPAPI 不可用，比如非 Windows 环境）：**AES-256-GCM**，
   密钥 = PBKDF2(机器名 + 用户名 + MAC + 固定盐)，每条随机 nonce。
   强度弱于 DPAPI，但远好于 base64，且不会因为系统限制直接崩溃。
3. 兼容旧格式：没有前缀的值按旧版 base64 解码，读进内存后下次保存自动升级为密文。

密文格式
--------
    dp1:<base64(DPAPI blob)>
    aes1:<base64(nonce12 + tag16 + ciphertext)>
    旧配置无前缀 → base64(utf-8 明文)
"""
import base64
import ctypes
import os
import uuid
from ctypes import wintypes

PREFIX_DPAPI = "dp1:"
PREFIX_AES = "aes1:"

# 应用专属 entropy：同一台机器上，别的程序不知道这段盐就解不开我们的 blob
_ENTROPY = b"GiWiFi-AutoLogin::credential::v1"

_AES_SALT = b"giwifi-aes-fallback-v1"
_AES_ITERATIONS = 120_000


# ── DPAPI ────────────────────────────────────────────────
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes):
    """构造 DATA_BLOB，并返回 (blob, buf)；buf 必须由调用方持有以防被回收"""
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf


def _dpapi_available() -> bool:
    return os.name == "nt"


def _dpapi_encrypt(data: bytes):
    """失败返回 None（调用方转 AES 兜底）"""
    if not _dpapi_available():
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR,
            ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        blob_in, _buf_in = _make_blob(data)
        blob_entropy, _buf_entropy = _make_blob(_ENTROPY)
        blob_out = _DATA_BLOB()

        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), "GiWiFi credential",
            ctypes.byref(blob_entropy), None, None, 0,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))
    except Exception:
        return None


def _dpapi_decrypt(blob: bytes):
    """失败返回 None"""
    if not _dpapi_available():
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        blob_in, _buf_in = _make_blob(blob)
        blob_entropy, _buf_entropy = _make_blob(_ENTROPY)
        blob_out = _DATA_BLOB()

        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None,
            ctypes.byref(blob_entropy), None, None, 0,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))
    except Exception:
        return None


# ── AES-GCM 兜底 ────────────────────────────────────────
def _fallback_key() -> bytes:
    from Crypto.Hash import SHA256
    from Crypto.Protocol.KDF import PBKDF2

    seed = "|".join([
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERDOMAIN", ""),
        os.environ.get("USERNAME", ""),
        f"{uuid.getnode():012x}",
        _ENTROPY.decode("utf-8"),
    ])
    return PBKDF2(seed, _AES_SALT, dkLen=32,
                  count=_AES_ITERATIONS, hmac_hash_module=SHA256)


def _aes_encrypt(data: bytes) -> str:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes

    cipher = AES.new(_fallback_key(), AES.MODE_GCM, nonce=get_random_bytes(12))
    ct, tag = cipher.encrypt_and_digest(data)
    return base64.b64encode(cipher.nonce + tag + ct).decode("ascii")


def _aes_decrypt(payload: str) -> str:
    from Crypto.Cipher import AES

    raw = base64.b64decode(payload.encode("ascii"))
    nonce, tag, ct = raw[:12], raw[12:28], raw[28:]
    cipher = AES.new(_fallback_key(), AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ct, tag).decode("utf-8")


# ── 对外接口 ────────────────────────────────────────────
def encrypt_secret(plain: str) -> str:
    """明文 → 密文（空串原样返回，保持配置文件干净）"""
    if not plain:
        return ""
    data = plain.encode("utf-8")
    blob = _dpapi_encrypt(data)
    if blob is not None:
        return PREFIX_DPAPI + base64.b64encode(blob).decode("ascii")
    return PREFIX_AES + _aes_encrypt(data)


def decrypt_secret(token: str) -> str:
    """密文 → 明文；兼容旧版 base64；解不开时返回空串（不残留半截乱码）"""
    if not token:
        return ""
    token = str(token)

    if token.startswith(PREFIX_DPAPI):
        raw = _dpapi_decrypt(base64.b64decode(token[len(PREFIX_DPAPI):].encode("ascii")))
        if raw is not None:
            try:
                return raw.decode("utf-8")
            except Exception:
                return ""
        return ""
    if token.startswith(PREFIX_AES):
        try:
            return _aes_decrypt(token[len(PREFIX_AES):])
        except Exception:
            return ""

    # 旧版：裸 base64 明文
    try:
        return base64.b64decode(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token  # 万一当初就存了明文


def is_encrypted(token: str) -> bool:
    return isinstance(token, str) and (
        token.startswith(PREFIX_DPAPI) or token.startswith(PREFIX_AES)
    )
