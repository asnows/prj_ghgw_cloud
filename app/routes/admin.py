"""管理后台路由：发卡 / 用户 / 激活码 / 用量（需 ADMIN_TOKEN）。"""
import json

from fastapi import APIRouter, Header, HTTPException

from ..auth import issue_license
from ..database import db

router = APIRouter(prefix="/admin", tags=["管理"])


def _guard(token: str):
    from ..config import get_settings
    if token != get_settings().ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权")


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


@router.get("/licenses")
def admin_licenses(x_admin_token: str = Header(default="")):
    """激活码列表。"""
    _guard(x_admin_token)
    with db() as conn:
        rows = conn.execute(
            "SELECT code, plan, expires_at, status, devices, created_at FROM licenses ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/revoke")
def admin_revoke(payload: dict, x_admin_token: str = Header(default="")):
    """停用激活码（退款/违规）。"""
    _guard(x_admin_token)
    code = (payload or {}).get("code", "")
    with db() as conn:
        conn.execute("UPDATE licenses SET status='revoked' WHERE code=?", (code,))
    return {"ok": True, "code": code}


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
