"""趋势因子：均线排列 + 价格位置 + 中期趋势（方案 §4.3-A）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class TrendFactor(BaseFactor):
    name = "trend"
    scopes = ["both", "index"]
    weight = 0.25

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        if df is None or len(df) < 30:
            return FactorResult(0.0, "趋势因子：历史数据不足", 0.0)

        close = df["close"]
        cfg = ctx.config
        windows = cfg.get("ma_windows", [5, 10, 20, 60])
        ma5, ma10, ma20, ma60 = (ind.ma(close, n) for n in windows)
        c = self._latest(close)
        m5, m10, m20, m60 = map(self._latest, (ma5, ma10, ma20, ma60))

        # 1) 均线排列
        if m5 > m10 > m20:
            align = 1.0
        elif m5 < m10 < m20:
            align = -1.0
        elif m5 > m20:
            align = 0.3
        else:
            align = -0.3

        # 2) 价格相对 MA20 位置（±8% 线性映射）
        pos = 0.0 if m20 == 0 else (c - m20) / abs(m20)
        pos_score = max(-1.0, min(1.0, pos / 0.08))

        # 3) 中期趋势 MA20 vs MA60
        mid = 0.4 if m20 >= m60 else -0.4

        score = 0.4 * align + 0.3 * pos_score + 0.3 * mid
        detail = (f"均线排列{'多头' if align > 0 else '空头' if align < 0 else '混合'}"
                  f"，价格偏离MA20 {pos * 100:+.1f}%"
                  f"，MA20{'>' if m20 >= m60 else '<'}MA60")
        return FactorResult(round(score, 4), detail, 1.0)
