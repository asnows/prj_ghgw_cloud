"""HTML 报告渲染：将终端文本报告（markdown 风格）渲染为带品牌 Logo 的 HTML 页面。

用法：
    from report_html import save_report_html
    save_report_html(report_text, out_path, title="个股分析报告")

说明：
    - Logo 以 base64 内嵌，单 HTML 文件即可分享，无外部依赖。
    - 配色呼应 logo：深海蓝背景 + 紫色主题 + 金色点缀。
"""
import base64
import os
import markdown

LOGO_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "assets", "logo.png"
)
# 候选 logo 路径（依次回退）：技能内 assets → 工作区 logo 目录
_LOGO_CANDIDATES = (
    LOGO_DEFAULT,
    "/sandbox/workspace/logo/gu_hai_guai_wu_logo_512.png",
    "/sandbox/workspace/logo/gu_hai_guai_wu_logo_1024.png",
)

CSS = """
:root {
  --deep: #0B2554; --deeper: #060F26;
  --purple: #7C3AED; --purple-dark: #5B21B6;
  --gold: #F59E0B; --gold-light: #FCD34D;
  --red: #E11D48; --green: #10B981;
  --ink: #1E293B; --muted: #64748B; --line: #E2E8F0;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: linear-gradient(160deg, #0B2554 0%, #060F26 100%);
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--ink);
  min-height: 100vh;
}
.wrap { max-width: 880px; margin: 0 auto; padding: 36px 16px 48px; }
.header { text-align: center; padding: 18px 20px 8px; }
.logo {
  width: 132px; height: 132px; border-radius: 50%;
  box-shadow: 0 0 46px rgba(245, 158, 11, 0.35), 0 0 18px rgba(124, 58, 237, 0.5);
}
.brand { color: #FFFFFF; font-size: 32px; font-weight: 800; letter-spacing: 6px; margin: 14px 0 4px; }
.brand-sub { color: var(--gold-light); font-size: 14px; letter-spacing: 3px; margin: 0; }
.card {
  background: #FFFFFF; border-radius: 18px;
  padding: 34px 42px; margin-top: 30px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}
.card h1, .card h2, .card h3 { color: var(--purple-dark); line-height: 1.4; }
.card h1 { font-size: 26px; border-bottom: 3px solid var(--gold); padding-bottom: 10px; }
.card h2 { font-size: 21px; margin-top: 30px; padding-left: 12px; border-left: 5px solid var(--purple); }
.card h3 { font-size: 17px; }
.card p { line-height: 1.85; color: #334155; }
.card ul, .card ol { line-height: 1.9; color: #334155; padding-left: 26px; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14.5px; }
th {
  background: linear-gradient(135deg, var(--purple), var(--purple-dark));
  color: #FFFFFF; font-weight: 700; padding: 10px 12px; text-align: left;
  border: 1px solid var(--purple-dark);
}
td { border: 1px solid var(--line); padding: 9px 12px; color: #334155; }
tr:nth-child(even) td { background: #F8FAFC; }
tr:hover td { background: #F3E8FF; }
strong { color: var(--purple-dark); }
hr { border: none; border-top: 2px dashed var(--line); margin: 22px 0; }
code { background: #F1F5F9; padding: 2px 7px; border-radius: 5px; font-size: 13px; color: var(--purple-dark); }
blockquote {
  margin: 14px 0; padding: 12px 18px;
  background: #FDF4E7; border-left: 5px solid var(--gold);
  color: #78350F; border-radius: 0 10px 10px 0;
}
.footer {
  text-align: center; color: #94A3B8; font-size: 12.5px;
  padding: 26px 10px 6px; line-height: 1.9;
}
.footer .brand-line { color: var(--gold-light); letter-spacing: 2px; }
"""


def _img_base64(path):
    """读取图片并转 base64 data URI（path 为空时自动搜索候选路径）。"""
    p = path
    if not p:
        for cand in _LOGO_CANDIDATES:
            if os.path.exists(cand):
                p = cand
                break
    if not p or not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    mime = "png" if ext in ("png",) else ("jpeg" if ext in ("jpg", "jpeg") else "svg+xml")
    return f"data:image/{mime};base64,{b64}"


def _preprocess(text):
    """预处理：markdown 表格要求前有空行，终端报告里表格紧跟标题行，需补空行。"""
    lines = text.split("\n")
    out = []
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("|") and out and out[-1].strip() and not out[-1].lstrip().startswith("|"):
            out.append("")
        out.append(ln)
    return "\n".join(out)


def text_to_html(report_text):
    md = markdown.Markdown(extensions=["tables", "sane_lists"])
    return md.convert(_preprocess(report_text))


def _paywall_html():
    """试用期已过时返回付费墙区块（内嵌收款码图片），否则返回空串。"""
    try:
        from license import license_status
        if license_status()["level"] != "expired":
            return ""
        pay_qr = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "pay_qr.png")
        qr_uri = _img_base64(pay_qr)
        qr_html = f'<img src="{qr_uri}" alt="收款码" style="width:210px;height:210px;border-radius:14px;box-shadow:0 6px 20px rgba(0,0,0,.15);"/>' if qr_uri else ""
        return f"""
<div style="margin-top:26px;padding:26px 22px;border-radius:14px;background:linear-gradient(135deg,#FDF4E7,#FEF3C7);border:1.5px dashed #F59E0B;text-align:center;">
  <div style="font-size:19px;font-weight:800;color:#92400E;">⏰ 免费试用已结束</div>
  <p style="color:#78350F;line-height:1.8;margin:12px 0 16px;">
    扫描下方收款码付费后，联系作者获取<b>激活码</b>（月卡/年卡可选）<br/>
    已有激活码？回复「激活 ghgw-XXXX-XXXX」即可解锁全部功能
  </p>
  {qr_html}
  <div style="margin-top:14px;color:#92400E;font-size:13px;">💳 扫码付费 → 领取激活码 → 回复「激活」解锁</div>
</div>"""
    except Exception:  # noqa: BLE001
        return ""


def render_html(report_text, title="股海怪物 · 分析报告", logo_path=None):
    logo_uri = _img_base64(logo_path)
    logo_html = (
        f'<img class="logo" src="{logo_uri}" alt="股海怪物"/>' if logo_uri
        else '<div class="logo" style="background:#7C3AED;"></div>'
    )
    body = text_to_html(report_text)
    paywall = _paywall_html()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    {logo_html}
    <div class="brand">股海怪物</div>
    <p class="brand-sub">SEA MONSTER · A股量化分析引擎</p>
  </div>
  <div class="card">
    {body}
    {paywall}
  </div>
  <div class="footer">
    <div class="brand-line">🐙 把模糊的市场感觉，转化为可量化的概率信号</div>
    <div>本报告由量化模型自动生成 · 仅供参考，不构成投资建议</div>
  </div>
</div>
</body>
</html>"""


def save_report_html(report_text, out_path, title="股海怪物 · 分析报告", logo_path=None):
    """渲染并保存 HTML 报告，返回保存路径。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_html(report_text, title=title, logo_path=logo_path))
    return out_path


if __name__ == "__main__":
    import sys
    demo = """# 个股分析报告

## 药明康德 603259

| 指标 | 数值 |
|------|------|
| 最新价 | 154.82 |
| 买入概率 | **73.5%**（高） |

> 本结果由量化模型生成，仅供参考，不构成投资建议。
"""
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo_report.html"
    save_report_html(demo, out, title="个股分析报告（示例）")
    print("saved:", out)
