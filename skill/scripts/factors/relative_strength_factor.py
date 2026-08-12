"""相对强弱因子：指数场景专属，衡量目标指数 vs 上证指数的强弱（方案 §4.4）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class RelativeStrengthFactor(BaseFactor):
    name = "relative_strength"
    scopes = ["index"]
    weight = 0.15

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        bench = ctx.benchmark
        if df is None or bench is None or len(df) < 25 or len(bench) < 25:
            return FactorResult(0.0, "相对强弱因子：基准数据不足", 0.5)

        lookback = ctx.config.get("lookback", 20)

        def _ret(series, n):
            v = self._latest(ind.returns(series, n))
            return v if not _is_nan(v) else 0.0

        sym_ret = _ret(df["close"], lookback)
        bench_ret = _ret(bench["close"], lookback)
        rel = sym_ret - bench_ret

        score = max(-1.0, min(1.0, rel / 0.03))  # ±3% -> ±1
        detail = (f"该指数近{lookback}日 {sym_ret * 100:+.1f}%"
                  f" vs 上证 {bench_ret * 100:+.1f}%"
                  f"，相对强弱 {rel * 100:+.1f}%")
        return FactorResult(round(score, 4), detail, 1.0)


def _is_nan(v):
    return v is None or v != v
