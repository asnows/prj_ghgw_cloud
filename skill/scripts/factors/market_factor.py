"""市场环境因子：大盘走势 + 行业相对强度（方案 §4.3-F，行业/个股场景）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class MarketFactor(BaseFactor):
    name = "market"
    scopes = ["both"]   # 指数场景停用（指数即市场，由 relative_strength 承接）
    weight = 0.15

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        market = ctx.market
        if df is None or market is None or len(df) < 10 or len(market) < 10:
            return FactorResult(0.0, "市场环境因子：数据不足", 0.5)

        lookback = ctx.config.get("lookback", 5)

        def _ret(series, n):
            v = self._latest(ind.returns(series, n))
            return v if not _is_nan(v) else 0.0

        mkt_ret = _ret(market["close"], lookback)
        sym_ret = _ret(df["close"], lookback)
        rel = sym_ret - mkt_ret  # 行业/个股相对大盘强度

        s_mkt = max(-0.5, min(0.5, mkt_ret / 0.02))          # 大盘 ±2% -> ±0.5
        s_rel = max(-0.5, min(0.5, rel / 0.03))              # 相对强度 ±3% -> ±0.5
        score = max(-1.0, min(1.0, s_mkt + s_rel))

        detail = (f"大盘近{lookback}日 {mkt_ret * 100:+.1f}%"
                  f"，标的相对强度 {rel * 100:+.1f}%")
        return FactorResult(round(score, 4), detail, 1.0)


def _is_nan(v):
    return v is None or v != v
