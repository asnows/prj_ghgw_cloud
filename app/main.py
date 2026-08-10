"""股海怪物云服务 入口：FastAPI 应用。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    # 或 python -m app.main
"""
import logging

from fastapi import FastAPI

from .config import get_settings
from .database import init_db
from .routes import admin, mcp, verify, webhook

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ghgw")

app = FastAPI(
    title="股海怪物云服务",
    description="支付自动闭环 + 激活码管理 + 分析能力 API",
    version="0.1.0",
)


@app.on_event("startup")
def _startup():
    init_db()
    logger.info("股海怪物云服务启动（env=%s, wxpay=%s）",
                get_settings().APP_ENV,
                "mock" if not get_settings().WXPAY_ENABLED else "production")


@app.get("/")
def root():
    return {
        "service": "股海怪物云服务",
        "endpoints": {
            "支付": "POST /pay/webhook（微信回调自动发码）",
            "创建支付": "POST /pay/create",
            "校验激活码": "POST /api/verify",
            "MCP 分析": "POST /mcp/analyze_stock",
            "管理后台": "/admin/*（需 X-Admin-Token）",
            "健康检查": "GET /api/health",
        },
    }


app.include_router(verify.router)
app.include_router(webhook.router)
app.include_router(admin.router)
app.include_router(mcp.router)


@app.post("/pay/create")
def pay_create(payload: dict):
    """创建支付单（返回 Native 扫码链接）。{"plan": "month|year"}"""
    plan = (payload or {}).get("plan", "month")
    return webhook.create_payment(plan)


if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run("app.main:app", host=cfg.HOST, port=cfg.PORT, reload=cfg.APP_ENV == "dev")
