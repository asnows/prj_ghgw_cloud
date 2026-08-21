"""客户自助购买：下单（口令金额法）→ 查询/自助取码。

口令金额法：每笔订单生成唯一"口令金额"（月卡 29.xx / 年卡 199.xx 随机尾数），
客户按口令金额付款到个人收款码 → 管理员后台核对金额后【确认收款并发卡】
→ 客户在查询页输入订单号取激活码。微信支付开通后可无缝切换全自动。
"""
import random
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from ..database import db

router = APIRouter(prefix="/order", tags=["购买"])

CN_TZ = ZoneInfo("Asia/Shanghai")

# 口令金额基础价（分）：月卡 29 元 / 年卡 199 元
_PLAN_BASE = {"month": 2900, "year": 19900}


def _gen_order_id() -> str:
    return datetime.now(CN_TZ).strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()


def _gen_amount(plan: str) -> int:
    """生成口令金额（分）：基础价 + 随机尾数 1~99 分（用于识别付款人）。"""
    base = _PLAN_BASE.get(plan, 2900)
    return base + random.randint(1, 99)


@router.post("/create")
def order_create(payload: dict):
    """下单：生成订单号 + 口令金额。返回订单信息供客户付款。"""
    plan = (payload or {}).get("plan", "month")
    if plan not in _PLAN_BASE:
        return {"code": 1, "msg": "未知套餐"}
    order_id = _gen_order_id()
    amount = _gen_amount(plan)
    with db() as conn:
        conn.execute(
            "INSERT INTO orders (order_id, platform, amount, plan, license_code, status, paid_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (order_id, "manual", amount, plan, None, "pending", ""),
        )
    return {"code": 0, "order_id": order_id, "amount": amount,
            "amount_yuan": f"{amount / 100:.2f}", "plan": plan}


@router.post("/query")
def order_query(payload: dict):
    """订单查询/自助取码：管理员确认收款后，此处返回激活码。"""
    order_id = ((payload or {}).get("order_id") or "").strip()
    if not order_id:
        return {"code": 1, "msg": "请输入订单号"}
    with db() as conn:
        row = conn.execute(
            "SELECT order_id, amount, plan, license_code, status, paid_at "
            "FROM orders WHERE order_id=%s", (order_id,)).fetchone()
        if not row:
            return {"code": 1, "msg": "订单不存在，请核对订单号"}
        d = dict(row)
        d["amount_yuan"] = f"{d['amount'] / 100:.2f}"
        return {"code": 0, "data": d}
