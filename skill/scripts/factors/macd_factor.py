"""MACD 因子：金叉/死叉 + 柱状图动能（方案 §4.3-D）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class MACDFactor(BaseFactor):
    name = "macd"
    scopes = ["both", "index"]
    weight = 0.15

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        if df is None or len(df) < 40:
            return FactorResult(0.0, "MACD因子：历史数据不足", 0.0)

        close = df["close"]
        cfg = ctx.config
        dif, dea, hist = ind.macd(close,
                                  cfg.get("fast", 12), cfg.get("slow", 26), cfg.get("signal", 9))

        dif_v, dea_v, hist_v = self._latest(dif), self._latest(dea), self._latest(hist)
        dif_p, dea_p = dif.iloc[-2], dea.iloc[-2]
        hist_p = hist.iloc[-2]

        cross_up = dif_p < dea_p and dif_v >= dea_v   # 金叉
        cross_down = dif_p > dea_p and dif_v <= dea_v  # 死叉
        hist_growing = hist_v > hist_p

        if cross_up and hist_v > 0:
            score, note = 0.8, "金叉且柱状图翻红"
        elif cross_down and hist_v < 0:
            score, note = -0.8, "死叉且柱状图翻绿"
        elif cross_up:
            score, note = 0.4, "金叉待确认"
        elif cross_down:
            score, note = -0.4, "死叉待确认"
        elif hist_growing:
            score, note = 0.3, "柱状图连续增长"
        else:
            score, note = -0.3, "柱状图连续萎缩"

        return FactorResult(round(score, 4),
                            f"MACD: {note}（DIF={dif_v:.3f} DEA={dea_v:.3f} HIST={hist_v:.3f}）", 1.0)
