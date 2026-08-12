"""统一报告模板：所有功能（F1~F4）输出遵循同一版式（品牌强化版）。

结构约定：
    🐙 股海怪物 · A股量化分析引擎
    ━━━━━━━━━━━━━━━━━━━━━━━━
    <功能标题>
    <元信息：时间 / 模式 / 标的>
    ━━━━━━━━━━━━━━━━━━━━━━━━
    <内容区块 1>
    <内容区块 2>
    ...
    ━━━━━━━━━━━━━━━━━━━━━━━━
    🐙 股海怪物 · <价值主张>
    ⚠️ 免责声明
"""

BRAND = "🐙 股海怪物"
BRAND_HEADER = "🐙 股海怪物 · A股量化分析引擎"
SLOGAN = "把模糊的市场感觉，转化为可量化的概率信号"
SEP = "━━━━━━━━━━━━━━━━━━━━━━━━"
DISCLAIMER = "⚠️ 本结果由量化模型生成，仅供参考，不构成投资建议。"


def header(title, meta=None):
    """报告头部：品牌独立行 + 标题 + 分隔线 + 可选元信息。"""
    lines = [BRAND_HEADER, SEP, str(title)]
    if meta:
        lines.append(str(meta))
    lines.append(SEP)
    return "\n".join(lines)


def section(title):
    """区块标题（自带前后空行）。"""
    return f"\n{title}\n"


def footer(extra=None):
    """尾部签名：品牌 + 价值主张 + 授权状态 + 免责（可附加说明行）。"""
    lines = [SEP, f"{BRAND} · {SLOGAN}"]
    if extra:
        lines.append(str(extra))
    try:
        from license import authorize_prompt
        lines.append(authorize_prompt())
    except Exception:  # noqa: BLE001 授权模块异常不影响报告
        pass
    lines.append(DISCLAIMER)
    return "\n".join(lines)
