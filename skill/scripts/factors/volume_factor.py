"""量能因子：价量配合判断（方案 §4.3-E）。"""
import indicators as ind
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class VolumeFactor(BaseFactor):
    name = "volume"
    scopes = ["both", "index"]
    weight = 0.10

    def compute(self, ctx: FactorContext) -> FactorResult:
        df = ctx.ohlcv
        if df is None or len(df) < 10:
            return FactorResult(0.0, "量能因子：历史数据不足", 0.0)

        # 涨跌幅：优先使用接口提供的 pct_chg 列，否则自行计算
        if "pct_chg" in df.columns:
            chg = self._latest(df["pct_chg"])
        else:
            chg = self._latest(df["close"].pct_change()) * 100

        window = ctx.config.get("volume_ratio_window", 5)
        vr = self._latest(ind.volume_ratio(df["volume"], window))

        if _is_nan(vr):
            return FactorResult(0.0, "量能因子：量比数据缺失", 0.5)

        if chg > 0 and vr > 1.2:
            score, note = 0.8, "价涨量增（资金确认）"
        elif chg < 0 and vr > 1.2:
            score, note = -0.8, "价跌量增（抛压显现）"
        elif chg > 0:
            score, note = 0.2, "价涨量缩（背离预警）"
        else:
            score, note = -0.2, "价跌量缩（抛压减弱）"

        return FactorResult(round(score, 4), f"量比={vr:.2f}，{note}", 1.0)


def _is_nan(v):
    return v is None or v != v
