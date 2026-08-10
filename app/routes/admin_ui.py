"""管理后台 Web 页面：浏览器可视化查看/管理 发卡、激活码、用户、用量。

访问：GET /admin（输入 ADMIN_TOKEN 登录）
数据：复用 /admin/* JSON API（X-Admin-Token 鉴权）
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["管理页面"])

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>🐙 股海怪物 · 管理后台</title>
<style>
  :root { --purple:#7C3AED; --deep:#0B2554; --gold:#F59E0B; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Noto Sans SC","PingFang SC",sans-serif;
         background:linear-gradient(160deg,#0B2554,#060F26); color:#1E293B; min-height:100vh; }
  .wrap { max-width:960px; margin:0 auto; padding:30px 16px 60px; }
  .header { text-align:center; color:#fff; margin-bottom:24px; }
  .header h1 { letter-spacing:4px; margin:0 0 6px; }
  .header p { color:#FCD34D; margin:0; font-size:14px; letter-spacing:2px; }
  .card { background:#fff; border-radius:14px; padding:22px 26px; margin-bottom:18px;
          box-shadow:0 10px 30px rgba(0,0,0,.3); }
  .card h2 { margin:0 0 14px; font-size:17px; color:var(--deep); border-left:5px solid var(--purple); padding-left:10px; }
  input, select, button { font-size:14px; padding:8px 12px; border-radius:8px; border:1px solid #CBD5E1; }
  input:focus, select:focus { outline:2px solid #A78BFA; }
  button { background:var(--purple); color:#fff; border:none; cursor:pointer; font-weight:600; }
  button:hover { background:#6D28D9; }
  button.ghost { background:#fff; color:var(--purple); border:1px solid var(--purple); }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { background:var(--purple); color:#fff; padding:8px 10px; text-align:left; }
  td { border-bottom:1px solid #E2E8F0; padding:7px 10px; }
  tr:hover td { background:#F5F3FF; }
  .badge { display:inline-block; padding:2px 8px; border-radius:20px; font-size:12px; }
  .badge.active { background:#DCFCE7; color:#15803D; }
  .badge.revoked { background:#FEE2E2; color:#B91C1C; }
  .stat { display:inline-block; background:#F5F3FF; border-radius:10px; padding:10px 18px; margin-right:10px; }
  .stat b { font-size:22px; color:var(--purple); display:block; }
  .stat span { font-size:12px; color:#64748B; }
  .msg { padding:10px 14px; border-radius:8px; margin:10px 0; font-size:13px; }
  .msg.ok { background:#DCFCE7; color:#15803D; }
  .msg.err { background:#FEE2E2; color:#B91C1C; }
  .login { max-width:380px; margin:120px auto; background:#fff; border-radius:14px; padding:30px; text-align:center; }
  .login h2 { color:var(--deep); }
  .login input { width:100%; margin:10px 0; }
  .login button { width:100%; margin-top:8px; }
</style>
</head>
<body>
<div class="wrap" id="loginBox">
  <div class="login">
    <div style="font-size:40px;">🐙</div>
    <h2>股海怪物 · 管理后台</h2>
    <input id="tokenInput" type="password" placeholder="输入 ADMIN_TOKEN"/>
    <button onclick="login()">进入管理</button>
    <div id="loginMsg"></div>
  </div>
</div>

<div class="wrap" id="mainBox" style="display:none;">
  <div class="header">
    <h1>🐙 股海怪物 · 管理后台</h1>
    <p>发卡 · 激活码 · 用量 · 用户</p>
  </div>

  <div class="card" style="display:flex; gap:14px; align-items:center;">
    <h2 style="flex:0 0 auto; margin:0;">📊 概览</h2>
    <div class="stat"><b id="statTotal">-</b><span>总激活码</span></div>
    <div class="stat"><b id="statActive">-</b><span>有效</span></div>
    <div class="stat"><b id="statCalls">-</b><span>总调用</span></div>
    <button class="ghost" onclick="logout()" style="margin-left:auto;">退出</button>
  </div>

  <div class="card">
    <h2>💳 手动发卡</h2>
    <select id="planSel">
      <option value="month">月卡（30天）</option>
      <option value="year">年卡（365天）</option>
    </select>
    <input id="countInput" type="number" value="1" min="1" max="200" style="width:80px;"/>
    <button onclick="issue()">生成激活码</button>
    <div id="issueMsg"></div>
    <div id="issueResult" style="margin-top:10px; font-size:13px; word-break:break-all;"></div>
  </div>

  <div class="card">
    <h2>🔑 激活码列表（最近 200）</h2>
    <table>
      <thead><tr><th>激活码</th><th>套餐</th><th>到期日</th><th>状态</th><th>绑定设备</th><th>操作</th></tr></thead>
      <tbody id="licBody"></tbody>
    </table>
  </div>

  <div class="card">
    <h2>🧾 订单记录（付款→发码）</h2>
    <table>
      <thead><tr><th>订单号</th><th>平台</th><th>金额(分)</th><th>套餐</th><th>关联激活码</th><th>付款时间</th></tr></thead>
      <tbody id="orderBody"></tbody>
    </table>
  </div>

  <div class="card">
    <h2>📈 最近用量</h2>
    <table>
      <thead><tr><th>激活码</th><th>工具</th><th>时间</th></tr></thead>
      <tbody id="usageBody"></tbody>
    </table>
  </div>
</div>

<script>
let TOKEN = localStorage.getItem('ghgw_admin_token') || '';
function api(path, method, body) {
  return fetch(path, {
    method: method || 'GET',
    headers: {'Content-Type':'application/json','X-Admin-Token':TOKEN},
    body: body ? JSON.stringify(body) : undefined
  }).then(r => r.json());
}
function login() {
  TOKEN = document.getElementById('tokenInput').value.trim();
  localStorage.setItem('ghgw_admin_token', TOKEN);
  api('/admin/licenses').then(d => {
    if (Array.isArray(d)) { showMain(); }
    else { document.getElementById('loginMsg').innerHTML = '<div class="msg err">Token 无效</div>'; }
  });
}
function logout() { localStorage.removeItem('ghgw_admin_token'); location.reload(); }
function showMain() {
  document.getElementById('loginBox').style.display = 'none';
  document.getElementById('mainBox').style.display = 'block';
  loadAll();
}
function loadAll() {
  api('/admin/licenses').then(d => {
    if (!Array.isArray(d)) return;
    const body = document.getElementById('licBody');
    body.innerHTML = d.map(l => {
      const devs = JSON.parse(l.devices || '[]');
      return `<tr><td style="font-family:monospace;font-size:12px;">${l.code}</td>
        <td>${l.plan==='year'?'年卡':'月卡'}</td>
        <td>${l.expires_at}</td>
        <td><span class="badge ${l.status}">${l.status==='active'?'有效':'停用'}</span></td>
        <td>${devs.length} 台</td>
        <td>${l.status==='active' ? `<button class="ghost" onclick="revoke('${l.code}')">停用</button>` : ''}</td></tr>`;
    }).join('');
    document.getElementById('statTotal').textContent = d.length;
    document.getElementById('statActive').textContent = d.filter(x=>x.status==='active').length;
  });
  api('/admin/usage').then(d => {
    if (!d || !d.recent) return;
    document.getElementById('statCalls').textContent = d.total_calls || 0;
    document.getElementById('usageBody').innerHTML = d.recent.map(u =>
      `<tr><td style="font-family:monospace;font-size:12px;">${u.license_code||'-'}</td>
       <td>${u.tool}</td><td>${u.ts}</td></tr>`).join('');
  });
  api('/admin/orders').then(d => {
    if (!Array.isArray(d)) return;
    document.getElementById('orderBody').innerHTML = d.map(o =>
      `<tr><td style="font-family:monospace;font-size:12px;">${o.order_id}</td>
       <td>${o.platform}</td><td>${o.amount}</td><td>${o.plan==='year'?'年卡':'月卡'}</td>
       <td style="font-family:monospace;font-size:12px;">${o.license_code||'-'}</td><td>${o.paid_at}</td></tr>`).join('');
  });
}
function issue() {
  const plan = document.getElementById('planSel').value;
  const count = parseInt(document.getElementById('countInput').value) || 1;
  api('/admin/issue','POST',{plan,count}).then(d => {
    if (d.codes) {
      document.getElementById('issueMsg').innerHTML = '<div class="msg ok">✅ 已生成 '+d.codes.length+' 个</div>';
      document.getElementById('issueResult').innerHTML =
        '<b>激活码（复制发给客户）：</b><br/>' + d.codes.map(c => `<div style="font-family:monospace;background:#F5F3FF;padding:4px 8px;margin:3px 0;border-radius:6px;">${c}</div>`).join('');
      loadAll();
    } else {
      document.getElementById('issueMsg').innerHTML = '<div class="msg err">' + (d.detail||'失败') + '</div>';
    }
  });
}
function revoke(code) {
  if (!confirm('确认停用该激活码？客户将立即无法使用。')) return;
  api('/admin/revoke','POST',{code}).then(() => { loadAll(); });
}
if (TOKEN) { api('/admin/licenses').then(d => { if (Array.isArray(d)) showMain(); }); }
</script>
</body>
</html>"""


@router.get("", response_class=HTMLResponse)
def admin_page():
    return PAGE
