"""RSI 因子：超买超卖 + 趋势修正（方案 §4.3-C）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class RSIFactor(BaseFactor):
    name = "rsi"
    scopes = ["both", "index"]
    weight = 0.15

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        if df is None or len(df) < 30:
            return FactorResult(0.0, "RSI因子：历史数据不足", 0.0)

        close = df["close"]
        period = ctx.config.get("period", 14)
        r = self._latest(ind.rsi(close, period))
        ma20 = self._latest(ind.ma(close, 20))
        ma60 = self._latest(ind.ma(close, 60))
        bullish = ma20 >= ma60

        if r < 30:  # 超卖
            score = 0.6 if bullish else 0.2   # 空头趋势中超卖=弱势，降低反弹预期
            note = "超卖"
        elif r > 70:  # 超买
            score = -0.2 if bullish else -0.6  # 多头强趋势中超买可容忍，减分
            note = "超买"
        else:
            score = max(-0.3, min(0.3, (50 - r) / 50 * 0.3))
            note = "中性"

        return FactorResult(round(score, 4), f"RSI({period})={r:.1f}，{note}，趋势{'多' if bullish else '空'}", 1.0)
