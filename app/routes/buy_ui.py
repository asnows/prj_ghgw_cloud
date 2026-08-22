"""客户购买页 + 自助取码页（口令金额法）。

- GET /buy        购买页：套餐展示 + 下单 → 显示口令金额/订单号 + 付款指引
- GET /buy/query  取码页：输入订单号 → 查询付款状态 → 自助取激活码
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/buy", tags=["购买页"])

PAGE_BUY = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>🐙 股海怪物 · 激活码购买</title>
<style>
  :root { --purple:#7C3AED; --deep:#0B2554; --gold:#F59E0B; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"PingFang SC","Microsoft YaHei",sans-serif;
         background:linear-gradient(160deg,#0B2554,#060F26); min-height:100vh; }
  .wrap { max-width:720px; margin:0 auto; padding:24px 16px 48px; }
  .header { text-align:center; color:#fff; margin-bottom:20px; }
  .header h1 { letter-spacing:4px; margin:0 0 6px; font-size:26px; }
  .header p { color:#FCD34D; margin:0; font-size:13px; }
  .card { background:#fff; border-radius:14px; padding:22px; margin-bottom:16px; }
  .card h2 { margin:0 0 12px; font-size:18px; color:var(--deep); border-left:4px solid var(--purple); padding-left:10px; }
  .plan { display:flex; gap:12px; margin:14px 0; }
  .plan-item { flex:1; border:2px solid #E9D5FF; border-radius:12px; padding:16px; text-align:center; cursor:pointer; }
  .plan-item.active { border-color:var(--purple); background:#F9F5FF; }
  .plan-item .price { font-size:26px; font-weight:800; color:var(--purple); }
  .plan-item .desc { font-size:12px; color:#64748B; margin-top:4px; }
  button { width:100%; padding:13px; border:none; border-radius:10px; font-size:16px; font-weight:700;
           background:linear-gradient(135deg,var(--purple),#5B21B6); color:#fff; cursor:pointer; margin-top:6px; }
  button:disabled { opacity:.6; }
  .result { background:#F5F3FF; border-radius:10px; padding:16px; margin-top:14px; font-size:15px; line-height:1.9; display:none; }
  .result b { color:var(--purple); }
  .tip { font-size:12.5px; color:#64748B; line-height:1.8; }
  .link { text-align:center; margin-top:14px; }
  .link a { color:#C4B5FD; font-size:13px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>🐙 股海怪物 · 量化分析</h1>
    <p>A股行业/个股涨跌概率分析 · 激活码购买</p>
  </div>
  <div class="card">
    <h2>选择套餐</h2>
    <div class="plan">
      <div class="plan-item active" onclick="sel('month', this)">
        <div class="price">¥29</div>
        <div class="desc">月卡 · 30 天</div>
      </div>
      <div class="plan-item" onclick="sel('year', this)">
        <div class="price">¥199</div>
        <div class="desc">年卡 · 365 天</div>
      </div>
    </div>
    <button onclick="create()">立即下单</button>
    <div class="result" id="res"></div>
    <div class="tip" style="margin-top:12px;">
      付款方式：微信/支付宝扫下方收款码，按 <b>口令金额</b> 付款
      （例：29.37 元）→ 联系客服确认到账 → 凭订单号到
      <a href="/buy/query" style="color:var(--purple);">取码页</a> 领取激活码。
    </div>
  </div>
  <div class="link"><a href="/buy/query">已有订单？去取激活码 →</a></div>
</div>
<script>
let plan = 'month';
function sel(p, el) {
  plan = p;
  document.querySelectorAll('.plan-item').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
}
async function create() {
  const btn = document.querySelector('button'); btn.disabled = true;
  const r = await fetch('/order/create', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({plan})});
  const d = await r.json();
  if (d.code === 0) {
    document.getElementById('res').style.display = 'block';
    if (d.pay_mode === 'alipay' && d.qr_img) {
      // 支付宝当面付：展示收款码 + 订单号（付款后自动发卡，可直接取码）
      document.getElementById('res').innerHTML =
        `<div style="font-size:16px;font-weight:700;">🎉 订单已生成，请扫码付款</div>
         <div style="margin-top:8px;">订单号：<b>${d.order_id}</b></div>
         <div style="margin-top:12px;text-align:center;">
           <img src="${d.qr_img}" style="width:220px;height:220px;border-radius:10px;border:1px solid #E9D5FF;"/>
         </div>
         <div class="tip" style="margin-top:10px;">打开支付宝【扫一扫】扫码付款 ¥<b style="color:#7C3AED;">${d.amount_yuan}</b>。
         付款成功后自动发卡，到 <a href="/buy/query" style="color:#7C3AED;">取码页</a> 输入订单号领取激活码。</div>`;
    } else {
      document.getElementById('res').innerHTML =
        `<div style="font-size:16px;font-weight:700;">🎉 下单成功！</div>
         <div style="margin-top:8px;">订单号：<b>${d.order_id}</b>（请保存）</div>
         <div>请支付口令金额：<b style="font-size:22px;color:#7C3AED;">¥${d.amount_yuan}</b></div>
         <div class="tip" style="margin-top:8px;">付款后联系客服确认到账，再到取码页输入订单号领取激活码。</div>`;
    }
  } else {
    alert('下单失败：' + d.msg);
  }
  btn.disabled = false;
}
</script>
</body>
</html>"""

PAGE_QUERY = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>🐙 股海怪物 · 激活码领取</title>
<style>
  :root { --purple:#7C3AED; --deep:#0B2554; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"PingFang SC","Microsoft YaHei",sans-serif;
         background:linear-gradient(160deg,#0B2554,#060F26); min-height:100vh; }
  .wrap { max-width:560px; margin:0 auto; padding:32px 16px 48px; }
  .card { background:#fff; border-radius:14px; padding:24px; }
  .card h1 { margin:0 0 16px; font-size:20px; color:var(--deep); text-align:center; }
  input { width:100%; padding:12px; border:1px solid #CBD5E1; border-radius:8px; font-size:15px; }
  button { width:100%; padding:12px; margin-top:12px; border:none; border-radius:8px; font-size:15px; font-weight:700;
           background:linear-gradient(135deg,#7C3AED,#5B21B6); color:#fff; cursor:pointer; }
  .result { margin-top:16px; display:none; }
  .box { background:#F5F3FF; border:1px dashed #7C3AED; border-radius:10px; padding:16px; text-align:center; }
  .box .code { font-size:15px; word-break:break-all; color:#5B21B6; font-family:monospace; }
  .warn { background:#FEF3C7; border-radius:10px; padding:14px; font-size:13px; color:#78350F; line-height:1.7; }
  .pending { background:#F0F9FF; border-radius:10px; padding:14px; font-size:13px; color:#075985; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>🐙 领取激活码</h1>
    <input id="oid" placeholder="输入订单号（下单时生成，如 20260822-ABC123）"/>
    <button onclick="query()">查询</button>
    <div class="result" id="res"></div>
  </div>
</div>
<script>
async function query() {
  const oid = document.getElementById('oid').value.trim();
  if (!oid) { alert('请输入订单号'); return; }
  const r = await fetch('/order/query', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({order_id: oid})});
  const d = await r.json();
  const res = document.getElementById('res');
  res.style.display = 'block';
  if (d.code !== 0) {
    res.innerHTML = `<div class="warn">⚠️ ${d.msg}</div>`;
    return;
  }
  const o = d.data;
  if (o.status === 'paid' && o.license_code) {
    res.innerHTML = `<div class="box">
      <div style="font-size:15px;font-weight:700;margin-bottom:8px;">🎉 激活码已生成</div>
      <div class="code">${o.license_code}</div>
      <div style="font-size:12px;color:#64748B;margin-top:10px;">复制后在 ima 输入「激活 激活码」即可解锁</div>
    </div>`;
  } else if (o.status === 'pending') {
    res.innerHTML = `<div class="pending">⏳ 订单待确认：您下单 ¥${o.amount_yuan}（${o.plan === 'year' ? '年卡' : '月卡'}），
      请按口令金额付款后联系客服确认。确认后刷新本页即可领取激活码。</div>`;
  } else {
    res.innerHTML = `<div class="warn">订单状态异常：${o.status}</div>`;
  }
}
</script>
</body>
</html>"""


@router.get("", response_class=HTMLResponse)
def buy_page():
    return HTMLResponse(PAGE_BUY)


@router.get("/query", response_class=HTMLResponse)
def query_page():
    return HTMLResponse(PAGE_QUERY)
