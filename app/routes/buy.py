"""客户自助购买：下单（口令金额法）→ 查询/自助取码。

口令金额法：每笔订单生成唯一"口令金额"（月卡 29.xx / 年卡 199.xx 随机尾数），
客户按口令金额付款到个人收款码 → 管理员后台核对金额后【确认收款并发卡】
→ 客户在查询页输入订单号取激活码。微信支付开通后可无缝切换全自动。
"""
import logging
import random
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from ..database import db

logger = logging.getLogger("ghgw.buy")

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
    """下单：支付宝启用时返回当面付收款码；否则口令金额模式（手动确认）。"""
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
    # 支付宝当面付模式：下单生成收款码（付款后回调自动发卡）
    from ..config import get_settings
    if get_settings().ALIPAY_ENABLED:
        try:
            from ..services import pay_alipay
            result = pay_alipay.precreate(order_id, f"{amount / 100:.2f}")
            qr_img = _qr_base64(result.get("qr_code", ""))
            return {"code": 0, "order_id": order_id, "amount": amount,
                    "amount_yuan": f"{amount / 100:.2f}", "plan": plan,
                    "pay_mode": "alipay", "qr_img": qr_img}
        except Exception as e:  # noqa: BLE001 支付宝失败降级口令金额
            logger.warning("支付宝下单失败，降级口令金额: %s", e)
    return {"code": 0, "order_id": order_id, "amount": amount,
            "amount_yuan": f"{amount / 100:.2f}", "plan": plan,
            "pay_mode": "manual"}


def _qr_base64(text: str) -> str:
    """将字符串转为二维码 PNG 的 base64 data URI（前端可直接 <img src> 展示）。"""
    try:
        import base64
        import io
        import qrcode
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001 二维码生成失败返回空
        return ""


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
