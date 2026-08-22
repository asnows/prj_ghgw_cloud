"""支付宝当面付：预下单（alipay.trade.precreate）+ 异步回调验签（RSA2）。

依赖：cryptography（RSA 签名）+ requests（HTTP 调用网关），无需外部支付宝 SDK。
环境变量（Railway）：
  ALIPAY_APPID       应用 AppID
  ALIPAY_PRIVATE_KEY 应用私钥（RSA2 PEM）
  ALIPAY_PUBLIC_KEY  支付宝公钥（RSA2 PEM）
"""
import base64
import json
import time
import urllib.parse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from ..config import get_settings

_GATEWAY = "https://openapi.alipay.com/gateway.do"


def _load_private_key(pem: str):
    return serialization.load_pem_private_key(pem.encode(), password=None)


def _load_public_key(pem: str):
    return serialization.load_pem_public_key(pem.encode())


def _sign_str(content: str, private_key) -> str:
    """RSA2 签名：SHA256withRSA，输出 base64。"""
    sig = private_key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _sign_params(params: dict, private_key) -> str:
    """按支付宝规范：剔除 sign/sign_type，参数按 key 升序拼接。"""
    items = sorted((k, v) for k, v in params.items() if v not in ("", None) and k not in ("sign", "sign_type"))
    content = "&".join(f"{k}={v}" for k, v in items)
    return _sign_str(content, private_key)


def _verify_sign(content: str, signature: str, public_key) -> bool:
    """RSA2 验签。"""
    try:
        public_key.verify(
            base64.b64decode(signature), content.encode("utf-8"),
            padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:  # noqa: BLE001
        return False


def _gateway_post(biz_content: dict, method: str) -> dict:
    """调用支付宝开放平台网关。"""
    cfg = get_settings()
    params = {
        "app_id": cfg.ALIPAY_APPID,
        "method": method,
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "biz_content": json.dumps(biz_content, ensure_ascii=False),
    }
    priv = _load_private_key(cfg.ALIPAY_PRIVATE_KEY)
    params["sign"] = _sign_params(params, priv)
    r = requests.post(_GATEWAY, data=params, timeout=15)
    data = r.json()
    resp_key = method.replace(".", "_") + "_response"
    resp = data.get(resp_key, {})
    if resp.get("code") != "10000":
        raise ValueError(f"支付宝接口错误: {resp.get('code')} {resp.get('msg')} {resp.get('sub_msg','')}")
    return resp


def precreate(order_id: str, amount_yuan: str, subject: str = "股海怪物激活码") -> dict:
    """当面付预下单：返回收款二维码 qr_code（客户扫码付款）。"""
    biz = {
        "out_trade_no": order_id,
        "total_amount": amount_yuan,
        "subject": subject,
        "timeout_express": "30m",
    }
    resp = _gateway_post(biz, "alipay.trade.precreate")
    return {"qr_code": resp.get("qr_code", ""), "out_trade_no": resp.get("out_trade_no", order_id)}


def verify_notify(params: dict) -> dict:
    """异步通知验签：成功返回通知数据，失败抛异常。"""
    cfg = get_settings()
    signature = params.get("sign", "")
    pub = _load_public_key(cfg.ALIPAY_PUBLIC_KEY)
    content = "&".join(
        f"{k}={v}" for k, v in sorted(params.items())
        if k not in ("sign", "sign_type") and v not in ("", None)
    )
    if not _verify_sign(content, signature, pub):
        raise ValueError("支付宝通知验签失败")
    return params


def is_notify_success(params: dict) -> bool:
    """通知是否支付成功。"""
    return params.get("trade_status") in ("TRADE_SUCCESS", "TRADE_FINISHED")
