"""盘中实时因子：今日动量 + 量比 + 盘口强度（仅盘中模式生效，方案 §4.5/§3.2）。"""
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class IntradayFactor(BaseFactor):
    name = "intraday"
    scopes = ["both", "index"]
    weight = 0.10

    def compute(self, ctx: FactorContext) -> FactorResult:
        if ctx.mode != "intraday":
            return FactorResult(0.0, "盘中因子：非盘中模式，未参与", 1.0)

        snap = ctx.snapshot or {}
        parts = []

        # 1) 今日涨跌幅（快照）
        chg = snap.get("pct_chg")
        if chg is None or chg != chg:
            return FactorResult(0.0, "盘中因子：快照缺失", 0.0)
        s_chg = max(-0.6, min(0.6, chg / 2.0))  # 今日 ±2% -> ±0.6
        parts.append(("今日动量", s_chg, f"今日 {chg:+.2f}%"))

        # 2) 量比（快照）
        vr = snap.get("volume_ratio")
        s_vr = 0.0
        if vr is not None and vr == vr:
            s_vr = max(-0.4, min(0.4, (vr - 1.0) / 1.0))
            parts.append(("量比", s_vr, f"量比 {vr:.2f}"))

        # 3) 盘口强度（五档委托量，可选）
        bid_ask = snap.get("bid_ask")
        s_ba = 0.0
        if isinstance(bid_ask, dict):
            bid = bid_ask.get("bid_vol", 0) or 0
            ask = bid_ask.get("ask_vol", 0) or 0
            if bid + ask > 0:
                s_ba = max(-0.2, min(0.2, (bid - ask) / (bid + ask)))
                parts.append(("盘口", s_ba, f"买盘占比 {bid / (bid + ask) * 100:.0f}%"))

        score = sum(p[1] for p in parts)
        detail = "；".join(f"{n} {d}" for n, _, d in parts)
        return FactorResult(round(score, 4), detail, 1.0)
