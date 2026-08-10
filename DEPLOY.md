# 部署上线指南

## 方案选择

| 平台 | 免费层 | 域名 | 说明 |
|------|--------|------|------|
| **Railway** | ✅ | 赠送 *.up.railway.app | 简单，自动 HTTPS |
| **Render** | ✅ | 赠送 *.onrender.com | 免费层冷启动较慢（15min 无流量休眠） |
| 自购云服务器 | ❌ | 需自备 | 国内节点需 ICP 备案；境外免备案 |

> 起步推荐 **Railway**：免费额度够个人项目，自动 HTTPS（微信回调要求 HTTPS）。

## 方式一：Railway 部署（推荐）

```bash
# 1. 安装 CLI 并登录（需 GitHub 账号授权）
npm i -g @railway/cli
railway login

# 2. 初始化（关联 gitee.com/471297974/prj_ghgw_cloud 或本地目录）
cd /sandbox/workspace/ghgw-cloud
railway init

# 3. 配置环境变量（Dashboard → Variables）
# 必填：
LICENSE_SECRET=   # python tools/gen_keys.py 生成
ADMIN_TOKEN=      # 自设强随机串
# 生产数据库（可选，免费层 SQLite 够起步；规模后再加）：
DATABASE_URL=postgresql://...   # Railway 可一键创建 PostgreSQL

# 4. 部署
railway up
# 或推送代码到仓库后，Railway 自动部署

# 5. 验证
curl https://你的服务.up.railway.app/api/health
```

## 方式二：Render 部署

1. 把 `prj_ghgw_cloud` 推到 GitHub（Render 支持 GitHub 关联）
2. Render → New → **Blueprint** → 选仓库（自动读取 render.yaml）
3. 按提示填写 LICENSE_SECRET / ADMIN_TOKEN（sync: false 的项）
4. 部署完成 → 访问 `https://ghgw-cloud.onrender.com/api/health`

## 方式三：自有服务器（Docker）

```bash
docker build -t ghgw-cloud .
docker run -d --name ghgw-cloud -p 8000:8000 \
  -e LICENSE_SECRET=xxx -e ADMIN_TOKEN=xxx \
  -e WXPAY_ENABLED=false \
  ghgw-cloud
```

## 微信支付对接（有商户号后）

1. `.env` 填写：
   ```
   WXPAY_ENABLED=true
   WXPAY_MCHID=商户号
   WXPAY_APPID=公众号/小程序 AppID
   WXPAY_APIV3_KEY=APIv3 密钥
   WXPAY_SERIAL_NO=商户证书序列号
   WXPAY_PRIVATE_KEY_PATH=/app/商户私钥.pem
   WXPAY_NOTIFY_URL=https://你的域名/pay/webhook
   ```
2. ⚠️ 当前 `pay_wechat.py` 的生产回调**验签为占位实现**（`verify_notify` 抛 NotImplementedError）——接入商户号时需补齐平台证书验签（代码注释已标注位置），或联系我完成。

## 上线检查清单

- [ ] `python -m tests.test_flow` 15 项全绿
- [ ] HTTPS 可达：`curl https://域名/api/health`
- [ ] 创建支付单返回真实 code_url（非 mock://）
- [ ] 微信回调 `/pay/webhook` 能收到通知并自动发码
- [ ] 管理后台用 ADMIN_TOKEN 能发卡/查列表
- [ ] skill 端 `license_pub.key` 与云服务 `LICENSE_SECRET` 一致（离线可校验）

## 常见问题

**Q: 免费层数据库会丢吗？**
A: Railway/Render 免费层磁盘非持久——**重启后 SQLite 数据可能丢失**。正式运营前务必切 PostgreSQL（DATABASE_URL 配置即可，代码已兼容）。

**Q: 冷启动慢？**
A: Render 免费层 15 分钟无流量会休眠，首次访问慢是正常的。Railway 无此问题。
