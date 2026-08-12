"""动量因子：短期/中期收益率 + 连涨连跌（方案 §4.3-B）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class MomentumFactor(BaseFactor):
    name = "momentum"
    scopes = ["both", "index"]
    weight = 0.20

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        if df is None or len(df) < 25:
            return FactorResult(0.0, "动量因子：历史数据不足", 0.0)

        close = df["close"]
        lookback = ctx.config.get("lookback", [5, 20])
        n_short, n_mid = lookback[:2] if len(lookback) >= 2 else (5, 20)

        r_short = self._latest(ind.returns(close, n_short))
        r_mid = self._latest(ind.returns(close, n_mid))

        # 短/中期动量 ±5% / ±10% 线性映射
        s_short = max(-1.0, min(1.0, r_short / 0.05)) if not _is_nan(r_short) else 0.0
        s_mid = max(-1.0, min(1.0, r_mid / 0.10)) if not _is_nan(r_mid) else 0.0

        # 连涨连跌
        cons = self._latest(ind.consecutive_days(close))
        s_cons = max(-1.0, min(1.0, cons / 5.0))

        score = 0.4 * s_short + 0.4 * s_mid + 0.2 * s_cons
        detail = (f"近{n_short}日 {r_short * 100:+.1f}%"
                  f"，近{n_mid}日 {r_mid * 100:+.1f}%"
                  f"，连{'涨' if cons > 0 else '跌' if cons < 0 else '平'}{abs(int(cons))}天")
        return FactorResult(round(score, 4), detail, 1.0)


def _is_nan(v):
    return v is None or v != v  # NaN 判断
