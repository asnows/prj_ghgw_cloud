"""波动率因子：高波动下调信号置信度（个股场景，方案 §4.5）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class VolatilityFactor(BaseFactor):
    name = "volatility"
    scopes = ["stock"]
    weight = 0.06

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        if df is None or len(df) < 20:
            return FactorResult(0.0, "波动率因子：历史数据不足", 0.5)

        period = ctx.config.get("atr_period", 14)
        high_level = ctx.config.get("high", 5.0)  # ATR 占比阈值 %
        atr_v = self._latest(ind.atr(df, period))
        price = self._latest(df["close"])

        if price <= 0:
            return FactorResult(0.0, "波动率因子：价格异常", 0.5)

        vol_ratio = atr_v / price * 100  # %
        if vol_ratio > high_level:
            confidence = 0.5
            note = "高波动，信号稳定性不足"
        else:
            confidence = 1.0
            note = "波动正常"

        # 波动率本身不贡献方向得分，仅影响置信度
        return FactorResult(0.0, f"ATR占比 {vol_ratio:.2f}%，{note}", confidence)
