"""管理后台路由：发卡 / 用户 / 激活码 / 用量 / 统计（需 ADMIN_TOKEN）。"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException

from ..auth import issue_license
from ..database import db

router = APIRouter(prefix="/admin", tags=["管理"])

CN_TZ = ZoneInfo("Asia/Shanghai")


def _guard(token: str):
    from ..config import get_settings
    if token != get_settings().ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权")


@router.get("/stats")
def admin_stats(x_admin_token: str = Header(default="")):
    """完整运营统计（概览看板数据）。"""
    _guard(x_admin_token)
    today = datetime.now(CN_TZ).date().isoformat()
    soon = (datetime.now(CN_TZ).date() + timedelta(days=7)).isoformat()
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM licenses").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) c FROM licenses WHERE status='active' AND expires_at >= %s", (today,)).fetchone()["c"]
        expired = conn.execute("SELECT COUNT(*) c FROM licenses WHERE status='active' AND expires_at < %s", (today,)).fetchone()["c"]
        expiring = conn.execute("SELECT COUNT(*) c FROM licenses WHERE status='active' AND expires_at >= %s AND expires_at <= %s", (today, soon)).fetchone()["c"]
        revoked = conn.execute("SELECT COUNT(*) c FROM licenses WHERE status='revoked'").fetchone()["c"]
        month_cards = conn.execute("SELECT COUNT(*) c FROM licenses WHERE plan='month'").fetchone()["c"]
        year_cards = conn.execute("SELECT COUNT(*) c FROM licenses WHERE plan='year'").fetchone()["c"]
        total_calls = conn.execute("SELECT COUNT(*) c FROM usage_logs").fetchone()["c"]
        order_count = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
        total_amount = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM orders").fetchone()["s"]
        month_start = today[:8] + "01"
        month_amount = conn.execute("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE paid_at >= %s", (month_start,)).fetchone()["s"]
        devices = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    return {
        "total": total, "active": active, "expired": expired, "expiring": expiring,
        "revoked": revoked, "month_cards": month_cards, "year_cards": year_cards,
        "total_calls": total_calls, "order_count": order_count,
        "total_amount": total_amount, "month_amount": month_amount, "devices": devices,
    }


@router.get("/licenses")
def admin_licenses(x_admin_token: str = Header(default=""), q: str = "", status: str = ""):
    """激活码列表（支持搜索/状态筛选）。"""
    _guard(x_admin_token)
    sql = "SELECT code, plan, expires_at, status, devices, created_at FROM licenses WHERE 1=1"
    args = []
    if q:
        sql += " AND code LIKE %s"
        args.append(f"%{q}%")
    if status:
        sql += " AND status=%s"
        args.append(status)
    sql += " ORDER BY id DESC LIMIT 300"
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


@router.post("/issue")
def admin_issue(payload: dict, x_admin_token: str = Header(default="")):
    """手动发卡：{"plan": "month|year", "count": n}"""
    _guard(x_admin_token)
    plan = (payload or {}).get("plan", "month")
    count = int((payload or {}).get("count", 1))
    if not 1 <= count <= 500:
        raise HTTPException(status_code=400, detail="count 需在 1-500")
    codes = [issue_license(plan) for _ in range(count)]
    return {"issued": len(codes), "codes": [c["code"] for c in codes]}


@router.post("/revoke")
def admin_revoke(payload: dict, x_admin_token: str = Header(default="")):
    """停用激活码（退款/违规）。"""
    _guard(x_admin_token)
    code = (payload or {}).get("code", "")
    with db() as conn:
        conn.execute("UPDATE licenses SET status='revoked' WHERE code=%s", (code,))
    return {"ok": True, "code": code}


@router.get("/orders")
def admin_orders(x_admin_token: str = Header(default="")):
    """订单记录（支付→发码 全链路）。"""
    _guard(x_admin_token)
    with db() as conn:
        rows = conn.execute(
            "SELECT order_id, platform, amount, plan, license_code, status, paid_at FROM orders ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/usage")
def admin_usage(x_admin_token: str = Header(default="")):
    """用量统计。"""
    _guard(x_admin_token)
    with db() as conn:
        rows = conn.execute(
            "SELECT license_code, tool, ts FROM usage_logs ORDER BY id DESC LIMIT 200"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS c FROM usage_logs").fetchone()["c"]
    return {"total_calls": total, "recent": [dict(r) for r in rows]}
