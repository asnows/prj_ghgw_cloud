# 股海怪物云服务（ghgw-cloud）

支付自动闭环 + 激活码管理 + 分析能力 API。**独立于 skill 代码仓库**，单独管理。

## 架构

```
客户扫码付款 → 微信支付 → /pay/webhook 自动发码 → 用户表
客户输入激活码 → /api/verify（签名+有效期+设备绑定）→ 放行
客户端分析 → /mcp/analyze_stock（复用 skill 引擎）→ 报告
管理员 → /admin/*（发卡/停用/用量）
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env            # 填 LICENSE_SECRET 等
python tools/gen_keys.py        # 生成签名密钥 → 写入 .env
python -m app.main              # 启动（默认 127.0.0.1:8000）
python -m tests.test_flow       # 全流程测试（15 项）
```

## 接口一览

| 端点 | 用途 | 鉴权 |
|------|------|------|
| `POST /pay/create` | 创建支付单（返回扫码链接） | 无 |
| `POST /pay/webhook` | 微信支付回调（自动发码） | 微信验签 |
| `POST /pay/mock/{no}` | MOCK 模拟付款（开发测试） | 仅 MOCK 模式 |
| `POST /api/verify` | 激活码+设备校验 | 激活码 |
| `POST /mcp/analyze_stock` | 个股分析 | 激活码 |
| `POST /mcp/analyze_industry` | 行业分析 | 激活码 |
| `GET /api/health` | 健康检查 | 无 |
| `POST /admin/issue` | 批量发卡 | X-Admin-Token |
| `GET /admin/licenses` | 激活码列表 | X-Admin-Token |
| `POST /admin/revoke` | 停用激活码 | X-Admin-Token |
| `GET /admin/usage` | 用量统计 | X-Admin-Token |

## 目录结构

```
app/
├── main.py           # FastAPI 入口
├── config.py         # 配置（环境变量）
├── database.py       # SQLite 数据层（生产可换 PostgreSQL）
├── auth.py           # 激活码生成/校验/设备绑定
├── routes/
│   ├── webhook.py    # 支付回调自动发码
│   ├── verify.py     # 激活码校验 API
│   ├── admin.py      # 管理后台
│   └── mcp.py        # 分析能力 API（复用 skill）
└── services/
    └── pay_wechat.py # 微信支付 V3（含 MOCK 模式）
tools/gen_keys.py     # 签名密钥生成
tests/test_flow.py    # 全流程测试
```

## 与 skill 的关系

| | skill（gu-hai-guai-wu） | 云服务（ghgw-cloud） |
|---|---|---|
| 定位 | 客户端分析引擎（本地计算） | 服务端鉴权/发卡/支付闭环 |
| 激活码 | 本地校验（离线降级） | 生成 + 联网校验（设备绑定） |
| 密钥 | `config/license_pub.key` | `.env` LICENSE_SECRET（两端一致） |
| 仓库 | 独立 | 独立 |

**两端密钥一致**：云服务 `LICENSE_SECRET` = skill 端 `config/license_pub.key`，客户端才能离线校验云服务发出的激活码。

## 上线检查清单

- [ ] 密钥：gen_keys.py 生成，两端配置一致（勿提交）
- [ ] 支付：开通微信支付商户号 → .env 填 WXPAY_* → WXPAY_ENABLED=true
- [ ] 服务器：境外节点起步免 ICP；境内需备案
- [ ] 部署：Railway/Render/云服务器 + PostgreSQL（生产）
- [ ] 域名：HTTPS 必配（微信回调要求）
- [ ] 测试：`python -m tests.test_flow` 全绿后上线

## 合规

- 产品定位"统计概率工具"，不构成投资建议（报告自带免责声明）
- 收款主体：个体工商户（微信商户支持）；月销<10万免增值税 + 经营所得减半（至 2027-12-31）
- 涉金融红线：不荐股、不承诺收益

## 已知限制（当前版本）

- SQLite 起步（单机）；生产切 PostgreSQL（database.py 已留 DATABASE_URL 切换口）
- 微信支付 V3 生产回调验签为 NotImplementedError 占位，接入商户号时补齐（见 pay_wechat.py 注释）
- MCP 端点为 HTTP-JSON 风格，非标准 MCP-SSE 协议（如需接入 Claude 等需 fastmcp 包装，见 skill 的 mcp_server.py）
