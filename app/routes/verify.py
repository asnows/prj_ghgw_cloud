"""激活码校验路由：客户端（ima skill / MCP 客户端）联网校验入口。"""
import logging

from fastapi import APIRouter

from ..auth import log_usage, verify_code

logger = logging.getLogger("ghgw.verify")
router = APIRouter(prefix="/api", tags=["鉴权"])


@router.post("/verify")
def verify(payload: dict):
    """校验激活码 + 设备指纹。成功返回会员状态；失败返回错误信息。"""
    code = (payload or {}).get("code", "")
    device = (payload or {}).get("device_fingerprint", "unknown")
    try:
        info = verify_code(code, device)
    except ValueError as e:
        return {"valid": False, "error": str(e)}
    log_usage(code, "verify", device)
    return info


@router.get("/health")
def health():
    return {"status": "ok", "service": "gu-hai-guai-wu-cloud"}
