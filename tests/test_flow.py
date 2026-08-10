"""全流程测试：模拟支付 → 自动发码 → 客户端校验 → 设备绑定 → 到期。

运行：python -m tests.test_flow
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("APP_ENV", "test")
# 注意：/sandbox/workspace 为 fuse 挂载，SQLite 无法写入；测试库放 /tmp
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test_ghgw.db")
os.environ.setdefault("LICENSE_SECRET", "test-secret-123456")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")

from app.database import init_db  # noqa: E402
from app.routes import webhook  # noqa: E402
from app.auth import verify_code, issue_license, make_code  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

CN_TZ = ZoneInfo("Asia/Shanghai")
PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


def main():
    init_db()

    print("\n=== 1. 创建支付单（MOCK） ===")
    order = webhook.create_payment("month")
    check("创建订单返回 code_url", bool(order.get("code_url")))
    out_trade_no = order["out_trade_no"]

    print("\n=== 2. 模拟客户付款（MOCK 回调） ===")
    from app.services import pay_wechat
    r = pay_wechat.mock_pay(out_trade_no)  # 同步生成"已付款"回调数据
    check("模拟付款成功", r["trade_state"] == "SUCCESS")
    # 触发发码逻辑
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post(f"/pay/mock/{out_trade_no}")
    data = resp.json()
    check("回调返回 OK", data.get("code") == "SUCCESS")
    license_code = data.get("license_code", "")
    check("自动发放激活码", license_code.startswith("ghgw-"))
    print(f"      激活码: {license_code}")

    print("\n=== 3. 客户端校验（含设备绑定） ===")
    r1 = verify_code(license_code, "device-A")
    check("设备A 校验通过", r1["valid"])
    r2 = verify_code(license_code, "device-B")
    check("设备B 校验通过", r2["valid"])
    try:
        verify_code(license_code, "device-C")
        verify_code(license_code, "device-D")
        check("设备数超限被拒", False)
    except ValueError:
        check("设备数超限被拒（默认3台）", True)

    print("\n=== 4. 伪造激活码拒绝 ===")
    fake = "ghgw-20991231-fake"
    try:
        verify_code(fake, "device-A")
        check("伪造码被拒", False)
    except ValueError:
        check("伪造码被拒", True)

    print("\n=== 5. 过期激活码拒绝 ===")
    past = make_code(datetime.now(CN_TZ) - timedelta(days=1))
    try:
        verify_code(past, "device-A")
        check("过期码被拒", False)
    except ValueError:
        check("过期码被拒", True)

    print("\n=== 6. API 层（FastAPI 客户端） ===")
    resp = client.post("/api/verify", json={"code": license_code, "device_fingerprint": "device-A"})
    check("POST /api/verify 有效", resp.json().get("valid") is True)
    resp = client.post("/api/verify", json={"code": "ghgw-20991231-fake", "device_fingerprint": "x"})
    check("POST /api/verify 拒绝伪造", resp.json().get("valid") is False)
    resp = client.get("/api/health")
    check("健康检查", resp.json()["status"] == "ok")

    print("\n=== 7. 管理后台 ===")
    resp = client.post("/admin/issue", json={"plan": "year", "count": 2},
                       headers={"X-Admin-Token": "test-admin-token"})
    check("批量发卡", resp.json().get("issued") == 2)
    resp = client.get("/admin/licenses", headers={"X-Admin-Token": "test-admin-token"})
    check("激活码列表", len(resp.json()) >= 3)
    resp = client.post("/admin/issue", json={"plan": "year", "count": 1})
    check("无 Token 被拒", resp.status_code == 401)

    print(f"\n===== 结果: {PASS} 通过 / {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
