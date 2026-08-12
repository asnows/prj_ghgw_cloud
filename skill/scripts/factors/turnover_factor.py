"""换手率因子：活跃度与过热/低迷判断（个股场景，方案 §4.5）。"""
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class TurnoverFactor(BaseFactor):
    name = "turnover"
    scopes = ["stock"]
    weight = 0.06

    def compute(self, ctx: FactorContext) -> FactorResult:
        cfg = ctx.config
        hot = cfg.get("hot", 15.0)
        cold = cfg.get("cold", 1.0)

        turnover = None
        if ctx.snapshot:
            turnover = ctx.snapshot.get("turnover")
        if turnover is None:
            df = ctx.ohlcv
            if df is not None and "turnover" in df.columns and len(df):
                turnover = self._latest(df["turnover"])

        if turnover is None or turnover != turnover:
            return FactorResult(0.0, "换手率因子：数据缺失", 0.5)

        if hot >= turnover > 8:
            score, note = 0.3, "健康活跃"
        elif turnover > hot:
            score, note = -0.5, "过热（防追高）"
        elif turnover < cold:
            score, note = -0.2, "低迷（关注度低）"
        else:
            score, note = 0.0, "中性"

        return FactorResult(round(score, 4), f"换手率 {turnover:.2f}%，{note}", 1.0)
