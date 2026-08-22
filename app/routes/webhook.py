"""支付回调路由：付款成功 → 自动发码（核心闭环）。"""
import logging

from fastapi import APIRouter, Request, Response

from ..auth import issue_license
from ..database import db, now_iso
from ..services import pay_wechat

logger = logging.getLogger("ghgw.webhook")
router = APIRouter(prefix="/pay", tags=["支付"])

# 订单号 -> 套餐（创建订单时暂存；生产建议入库 orders 表再查）
_PENDING = {}


def create_payment(plan: str) -> dict:
    """创建支付单（供支付页调用）。"""
    order = pay_wechat.create_native_order(plan)
    _PENDING[order["out_trade_no"]] = plan
    return order


@router.post("/alipay_notify")
async def alipay_notify(request: Request):
    """支付宝异步通知：验签 → 查单幂等 → 自动发码。"""
    from ..services import pay_alipay
    form = await request.form()
    params = dict(form)
    try:
        pay_alipay.verify_notify(params)
    except Exception as e:  # noqa: BLE001
        logger.warning("支付宝通知验签失败: %s", e)
        return {"code": "FAIL", "msg": "验签失败"}
    if not pay_alipay.is_notify_success(params):
        return {"code": "SUCCESS", "msg": "忽略非成功状态"}

    out_trade_no = params.get("out_trade_no", "")
    if not out_trade_no:
        return {"code": "FAIL", "msg": "缺少订单号"}
    # 幂等：同一订单只发一次码
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM orders WHERE order_id=%s", (out_trade_no,)).fetchone()
        if existing:
            return {"code": "SUCCESS", "msg": "订单已处理"}
        # 支付宝创建预下单时订单已存在（buy 模式）→ 直接取 plan 更新
        row = conn.execute(
            "SELECT plan FROM orders WHERE order_id=%s", (out_trade_no,)).fetchone()
        if row:
            plan = row["plan"]
        else:
            plan = "month"
        lic = issue_license(plan)
        conn.execute(
            "UPDATE orders SET platform='alipay', license_code=%s, status='paid', paid_at=%s "
            "WHERE order_id=%s",
            (lic["code"], now_iso(), out_trade_no),
        )
    logger.info("支付宝回调发卡成功: %s", lic["code"])
    return {"code": "SUCCESS", "msg": "成功"}


@router.post("/webhook")
async def wechat_notify(request: Request):
    """微信支付回调：验签 → 查单 → 发码 → 回执。"""
    body = await request.body()
    try:
        data = pay_wechat.verify_notify(body, dict(request.headers))
    except Exception as e:  # noqa: BLE001
        logger.warning("回调验签失败: %s", e)
        return Response(content='{"code":"FAIL","message":"验签失败"}', media_type="application/json", status_code=401)

    out_trade_no = data.get("out_trade_no", "")
    trade_state = data.get("trade_state", "SUCCESS")
    if trade_state != "SUCCESS":
        return {"code": "SUCCESS", "message": "忽略非成功状态"}

    # 幂等：同一订单只发一次码
    with db() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE order_id=%s", (out_trade_no,)).fetchone()
        if existing:
            return {"code": "SUCCESS", "message": "订单已处理"}

    plan = _PENDING.get(out_trade_no, "month")
    lic = issue_license(plan)
    with db() as conn:
        conn.execute(
            "INSERT INTO orders (order_id, platform, amount, plan, license_code, status, paid_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (out_trade_no, "wechat", data.get("amount", 0), plan, lic["code"], "paid", now_iso()),
        )
    logger.info("自动发码成功: 订单 %s → %s（%s）", out_trade_no, lic["code"], plan)
    return {"code": "SUCCESS", "message": "OK"}


@router.post("/mock/{out_trade_no}")
async def mock_pay(out_trade_no: str):
    """MOCK 模式：模拟客户付款完成（开发/测试用）。"""
    data = pay_wechat.mock_pay(out_trade_no)
    return await wechat_notify_logic(data)


async def wechat_notify_logic(data: dict):
    """与真实回调共用发码逻辑。"""
    out_trade_no = data.get("out_trade_no", "")
    if data.get("trade_state", "SUCCESS") != "SUCCESS":
        return {"code": "SUCCESS", "message": "忽略非成功状态"}
    with db() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE order_id=%s", (out_trade_no,)).fetchone()
        if existing:
            return {"code": "SUCCESS", "message": "订单已处理"}
    plan = _PENDING.get(out_trade_no, "month")
    lic = issue_license(plan)
    with db() as conn:
        conn.execute(
            "INSERT INTO orders (order_id, platform, amount, plan, license_code, status, paid_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (out_trade_no, "wechat-mock", data.get("amount", 0), plan, lic["code"], "paid", now_iso()),
        )
    return {"code": "SUCCESS", "message": "OK", "license_code": lic["code"]}
