"""资金面因子：主力资金净流入（个股场景，方案 §4.5）。"""
from .base import BaseFactor, FactorContext, FactorResult, register


@register
class FundFlowFactor(BaseFactor):
    name = "fund_flow"
    scopes = ["stock"]
    weight = 0.15

    def compute(self, ctx: FactorContext) -> FactorResult:
        ff = ctx.fund_flow or {}
        ratio = ff.get("main_net_ratio")  # 主力净流入占比（%）
        if ratio is None or ratio != ratio:  # NaN 检查
            return FactorResult(0.0, "资金面因子：资金流数据缺失", 0.0)

        score = max(-1.0, min(1.0, ratio / 5.0))  # ±5% -> ±1
        direction = "净流入" if ratio >= 0 else "净流出"
        return FactorResult(round(score, 4),
                            f"主力资金{direction} {ratio:+.2f}%", 1.0)
