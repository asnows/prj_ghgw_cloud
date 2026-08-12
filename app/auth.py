"""鉴权与发码核心：激活码生成 / 校验 / 设备绑定。

激活码格式与 skill 端 license.py 完全兼容：
    ghgw-YYYYMMDD-<HMAC-SHA256 签名>
这样客户端（ima skill）离线时也能本地校验（降级模式）。
"""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import get_settings
from .database import db, now_iso

CN_TZ = ZoneInfo("Asia/Shanghai")


def sign(payload: str) -> str:
    """HMAC-SHA256 签名（与 skill 端一致）。"""
    key = get_settings().LICENSE_SECRET.encode("utf-8")
    digest = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_code(expire_date: datetime, plan: str = "month") -> str:
    """生成激活码（按到期日 + 随机 nonce 保证唯一）。

    格式：ghgw-YYYYMMDD-<nonce6><sig>，nonce 取签名段前 6 字符。
    """
    exp = expire_date.strftime("%Y%m%d")
    nonce = secrets.token_hex(3)  # 6 字符
    payload = f"ghgw-{exp}-{nonce}"
    return f"ghgw-{exp}-{nonce}{sign(payload)}"


def _verify_signature(code: str, exp_str: str, sig_part: str) -> bool:
    """签名校验：优先新格式（nonce6+sig），兼容旧格式（纯 sig）。"""
    if len(sig_part) > 6:
        nonce, sig = sig_part[:6], sig_part[6:]
        if hmac.compare_digest(sig, sign(f"ghgw-{exp_str}-{nonce}")):
            return True
    return hmac.compare_digest(sig_part, sign(f"ghgw-{exp_str}"))


def issue_license(plan: str = "month") -> dict:
    """发码：生成激活码并写入 licenses 表。返回激活码信息。"""
    cfg = get_settings()
    plan_cfg = cfg.plans.get(plan)
    if not plan_cfg:
        raise ValueError(f"未知套餐: {plan}")
    days = plan_cfg["days"]
    expire = datetime.now(CN_TZ) + timedelta(days=days)
    code = make_code(expire)
    with db() as conn:
        conn.execute(
            "INSERT INTO licenses (code, plan, days, expires_at, status, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
            (code, plan, days, expire.strftime("%Y-%m-%d"), "active", now_iso()),
        )
    return {"code": code, "plan": plan, "expires_at": expire.strftime("%Y-%m-%d"), "days": days}


def verify_code(code: str, device_fingerprint: str) -> dict:
    """校验激活码（签名 + 有效期 + 设备绑定）。成功返回状态，失败抛出 ValueError。"""
    # 注意：签名（base64 urlsafe）本身可能含 "-"，故只分割前两段
    parts = (code or "").strip().split("-", 2)
    if len(parts) != 3 or parts[0] != "ghgw":
        raise ValueError("激活码格式错误")
    exp_str, sig = parts[1], parts[2]
    try:
        expire = datetime.strptime(exp_str, "%Y%m%d").date()
    except ValueError:
        raise ValueError("激活码格式错误")

    # 签名校验（新格式 nonce+sig，兼容旧格式纯 sig）
    if not _verify_signature(code, exp_str, sig):
        raise ValueError("激活码签名无效")

    with db() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE code=%s", (code,)).fetchone()
    if row is None:
        raise ValueError("激活码不存在（可能未发放）")
    if row["status"] != "active":
        raise ValueError("激活码已被停用")

    # 有效期（与 skill 端一致：>= 今日）
    from datetime import date
    if expire < date.today():
        raise ValueError(f"激活码已过期（{expire.isoformat()}）")

    # 设备绑定（防一码多用）
    devices = json.loads(row["devices"] or "[]")
    max_dev = get_settings().MAX_DEVICES_PER_LICENSE
    if device_fingerprint not in devices:
        if len(devices) >= max_dev:
            raise ValueError(f"设备数已达上限（{max_dev} 台），请联系管理员解绑")
        devices.append(device_fingerprint)
        with db() as conn:
            conn.execute("UPDATE licenses SET devices=%s WHERE code=%s", (json.dumps(devices), code))
        # 关联 user
        with db() as conn:
            u = conn.execute(
                "SELECT id FROM users WHERE device_fingerprint=%s", (device_fingerprint,)
            ).fetchone()
            if u is None:
                cur = conn.execute(
                    "INSERT INTO users (device_fingerprint, created_at) VALUES (%s,%s)",
                    (device_fingerprint, now_iso()),
                )
                uid = cur.lastrowid
            else:
                uid = u["id"]
            conn.execute("UPDATE licenses SET user_id=%s WHERE code=%s", (uid, code))

    return {
        "valid": True,
        "code": code,
        "plan": row["plan"],
        "expires_at": expire.isoformat(),
        "devices": len(devices),
        "max_devices": max_dev,
    }


def log_usage(code: str, tool: str, device_fingerprint: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO usage_logs (license_code, tool, device_fingerprint, ts) VALUES (%s,%s,%s,%s)",
            (code, tool, device_fingerprint, now_iso()),
        )
