"""MCP-SSE 端点：把股海怪物分析能力以 MCP 标准暴露给任意 agent。

鉴权：请求头 X-License-Code + X-Device-Fingerprint（或 MCP 工具参数传入）。
复用 skill 的 scripts 作为分析引擎（路径由 SKILL_DIR 配置）。
"""
import os
import sys

from fastapi import APIRouter, HTTPException

from ..auth import verify_code
from ..config import get_settings

router = APIRouter(prefix="/mcp", tags=["MCP"])

_engine_loaded = False


def _load_engine():
    """按需加载 skill 分析引擎（避免启动时依赖 akshare）。"""
    global _engine_loaded
    if _engine_loaded:
        return
    skill_dir = get_settings().SKILL_DIR
    scripts = os.path.join(skill_dir, "scripts")
    if not os.path.isdir(scripts):
        raise HTTPException(status_code=500, detail=f"SKILL_DIR 无效: {skill_dir}")
    sys.path.insert(0, scripts)
    _engine_loaded = True


def _check(code: str, device: str):
    if not code:
        raise HTTPException(status_code=401, detail="缺少激活码（X-License-Code）")
    try:
        return verify_code(code, device or "unknown")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/analyze_stock")
def analyze_stock(payload: dict):
    """个股分析（MCP 风格封装）。"""
    code = (payload or {}).get("license_code") or ""
    device = (payload or {}).get("device_fingerprint") or ""
    _check(code, device)
    _load_engine()
    from stock_analysis import StockAnalyzer  # noqa: E402
    from data_fetcher import DataFetcher  # noqa: E402
    from utils import load_config  # noqa: E402
    config = load_config()
    fetcher = DataFetcher(config)
    symbol = (payload or {}).get("symbol", "")
    return {"report": StockAnalyzer(config, fetcher).analyze(symbol)}


@router.post("/analyze_industry")
def analyze_industry(payload: dict):
    """行业分析。"""
    code = (payload or {}).get("license_code") or ""
    device = (payload or {}).get("device_fingerprint") or ""
    _check(code, device)
    _load_engine()
    from industry_analysis import IndustryAnalyzer  # noqa: E402
    from data_fetcher import DataFetcher  # noqa: E402
    from utils import load_config  # noqa: E402
    config = load_config()
    fetcher = DataFetcher(config)
    return {"report": IndustryAnalyzer(config, fetcher).run()}
