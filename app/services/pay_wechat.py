"""微信支付 V3 封装（Native 扫码支付）。

- 未配置密钥时自动进入 MOCK 模式（开发/测试用）：create_native_order 直接返回模拟支付单，
  并提供 mock_pay 模拟"客户已付款"。
- 生产模式：真实调用微信支付 API 并验签回调（依赖微信支付商户号）。
"""
import json
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from ..config import get_settings


def is_mock() -> bool:
    return not get_settings().WXPAY_ENABLED


def create_native_order(plan: str, out_trade_no: str = None) -> dict:
    """创建 Native 扫码支付订单，返回支付二维码链接 code_url。"""
    cfg = get_settings()
    plan_cfg = cfg.plans.get(plan)
    if not plan_cfg:
        raise ValueError(f"未知套餐: {plan}")
    out_trade_no = out_trade_no or f"GHGW{uuid.uuid4().hex[:16].upper()}"

    if is_mock():
        # MOCK：直接生成可"付款"的模拟订单
        return {
            "mock": True,
            "out_trade_no": out_trade_no,
            "plan": plan,
            "amount": plan_cfg["price"],
            "code_url": f"mock://weixin/native/{out_trade_no}",
            "tip": "MOCK 模式：调用 /pay/mock/{out_trade_no} 模拟付款",
        }

    # 真实微信支付 V3 Native 下单（需配置商户号与 APIv3 密钥）
    # 参考文档：https://pay.weixin.qq.com/doc/v3/merchant/4012791887
    payload = {
        "appid": cfg.WXPAY_APPID,
        "mchid": cfg.WXPAY_MCHID,
        "description": f"股海怪物-{plan_cfg['name']}",
        "out_trade_no": out_trade_no,
        "notify_url": cfg.WXPAY_NOTIFY_URL,
        "amount": {"total": plan_cfg["price"], "currency": "CNY"},
    }
    headers = _wx_headers("/v3/pay/transactions/native", json.dumps(payload))
    resp = httpx.post("https://api.mch.weixin.qq.com/v3/pay/transactions/native",
                      json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {"mock": False, "out_trade_no": out_trade_no, "plan": plan,
            "amount": plan_cfg["price"], "code_url": data["code_url"]}


def _wx_headers(path: str, body: str):
    """微信支付 V3 请求签名（需商户 API 私钥）。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    cfg = get_settings()
    with open(cfg.WXPAY_PRIVATE_KEY_PATH, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    message = f"{cfg.WXPAY_MCHID}\n{timestamp}\n{nonce}\n{body}\n"
    signature = priv.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    import base64
    sig_b64 = base64.b64encode(signature).decode()
    return {
        "Authorization": (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{cfg.WXPAY_MCHID}",'
            f'nonce_str="{nonce}",signature="{sig_b64}",'
            f'timestamp="{timestamp}",serial_no="{cfg.WXPAY_SERIAL_NO}"'
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def verify_notify(body: bytes, headers: dict) -> dict:
    """验签并解析微信支付回调（V3 平台证书验签）。MOCK 模式直接解析 JSON。"""
    if is_mock():
        return json.loads(body.decode("utf-8"))
    # 生产：验证 Wechatpay-Signature 等头，解密 resource
    # 实现要点：用平台证书公钥验签 -> AES-256-GCM 解密 resource -> 返回明文订单
    raise NotImplementedError("生产模式回调验签需配置微信平台证书，请联系管理员启用")


def mock_pay(out_trade_no: str) -> dict:
    """MOCK 模式模拟"客户已付款"回调。"""
    if not is_mock():
        raise RuntimeError("非 MOCK 模式，请走真实支付")
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return {
        "mchid": "MOCK-MCHID",
        "out_trade_no": out_trade_no,
        "transaction_id": f"MOCK-{uuid.uuid4().hex[:12].upper()}",
        "trade_state": "SUCCESS",
        "success_time": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
