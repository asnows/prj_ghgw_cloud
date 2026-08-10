"""手动联调演示：模拟 支付→发码→校验→后台 完整 HTTP 流程。

运行：python tools/demo_flow.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["LICENSE_SECRET"] = "test-demo-key"
os.environ["ADMIN_TOKEN"] = "demo-admin-token"
os.environ["DATABASE_URL"] = "sqlite:////tmp/demo_ghgw.db"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def main():
    # with 块触发 app startup（建表），贴近真实服务启动
    with TestClient(app) as client:
        print("=" * 60)
        print("🔧 股海怪物云服务 · 手动联调演示")
        print("=" * 60)

        print("\n【1】健康检查")
        r = client.get("/api/health")
        print("  GET /api/health →", r.json())

        print("\n【2】客户发起购买（月卡）")
        r = client.post("/pay/create", json={"plan": "month"})
        order = r.json()
        print("  POST /pay/create → 订单号:", order["out_trade_no"], "| 金额:", order["amount"], "分")
        print("  扫码链接:", order["code_url"])
        out_trade_no = order["out_trade_no"]

        print("\n【3】客户付款后，微信回调（MOCK 模拟）")
        r = client.post(f"/pay/mock/{out_trade_no}")
        data = r.json()
        print("  POST /pay/mock →", data)
        license_code = data.get("license_code", "")

        print("\n【4】客户在 ima 输入激活码，客户端联网校验")
        r = client.post("/api/verify", json={"code": license_code, "device_fingerprint": "device-A"})
        print("  设备A校验 →", r.json())

        print("\n【5】错误激活码校验（应拒绝）")
        r = client.post("/api/verify", json={"code": "ghgw-20991231-fake", "device_fingerprint": "x"})
        print("  伪造码 →", r.json())

        print("\n【6】管理员批量发年卡")
        r = client.post("/admin/issue", json={"plan": "year", "count": 3},
                        headers={"X-Admin-Token": "demo-admin-token"})
        issued = r.json()
        print("  POST /admin/issue → 发放", issued["issued"], "个")
        print("  示例码:", issued["codes"][0][:24] + "...")

        print("\n【7】管理员查看激活码列表")
        r = client.get("/admin/licenses", headers={"X-Admin-Token": "demo-admin-token"})
        print("  列表条数:", len(r.json()))

        print("\n【8】无 Token 访问后台（应 401 拒绝）")
        r = client.get("/admin/licenses")
        print("  状态码:", r.status_code)

        print("\n" + "=" * 60)
        print("✅ 全流程演示完成（模拟支付→自动发码→校验→后台管理）")


if __name__ == "__main__":
    main()
