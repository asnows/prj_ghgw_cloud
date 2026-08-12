"""概率引擎：因子调度 → 加权 → Sigmoid 概率映射 → 置信度聚合。

scoring 只做调度，不含任何因子业务逻辑（方案 §4.1/§4.2）。
"""
import math
from dataclasses import dataclass, field

from factors import get_factor_classes
from factors.base import FactorContext, FactorResult


@dataclass
class ScoreResult:
    S: float = 0.0              # 综合得分 ∈ [-1, 1]
    prob_up: float = 0.5        # 上涨概率
    prob_down: float = 0.5      # 下跌概率
    confidence: float = 1.0     # 置信度 [0, 1]
    factors: list = field(default_factory=list)  # [(name, FactorResult, weight)]


def _match_scopes(f_scopes, scope):
    """因子 scopes 匹配：scopes 含当前场景，或含 'both' 且场景为 行业/个股。"""
    if scope in f_scopes:
        return True
    return scope in ("industry", "stock") and "both" in f_scopes


def load_factor_entries(config, scopes):
    """按场景筛选启用的因子配置（scopes 为单个场景标签，如 'industry'/'stock'/'index'）。"""
    factors_cfg = config.get("factors", {})
    entries = []
    for name, fc in factors_cfg.items():
        if not fc.get("enabled", True):
            continue
        if not _match_scopes(fc.get("scopes", []), scopes):
            continue
        entries.append((name, fc))
    return entries


def compute_score(ctx: FactorContext, config, scopes) -> ScoreResult:
    """核心计算。ctx: FactorContext；config: 全局配置；scopes: 场景标签。

    若存在生效的 ML 调优版本（model/meta.json），用学习到的权重与偏置覆盖
    默认权重，并应用概率校准器（方案 §4.9）；否则使用纯规则引擎。
    """
    classes = get_factor_classes()
    entries = load_factor_entries(config, scopes)
    active_weights, calibrator = _load_active_model()

    results = []
    total_w = 0.0
    for name, fc in entries:
        cls = classes.get(name)
        if cls is None:
            continue
        try:
            factor = cls()
        except Exception:  # noqa: BLE001
            continue
        if active_weights:
            w = float(active_weights.get("weights", {}).get(name, 0.0) or 0.0)
        else:
            w = float(fc.get("weight", factor.weight) or 0.0)
        fctx = FactorContext(
            mode=ctx.mode,
            ohlcv=ctx.ohlcv,
            snapshot=ctx.snapshot,
            fund_flow=ctx.fund_flow,
            market=ctx.market,
            benchmark=ctx.benchmark,
            config=fc.get("params", {}) or {},
        )
        try:
            res = factor.compute(fctx)
        except Exception as e:  # noqa: BLE001 单因子异常不拖垮整体
            res = FactorResult(0.0, f"{name} 计算异常: {e}", 0.0)
        results.append((name, res, w))
        total_w += w

    # ML 模式下权重为逻辑回归系数（有正有负），total_w 可能 <= 0，
    # 不能据此判定"无有效因子"；仅当没有任何因子产出结果时才回退默认概率。
    if not results:
        return ScoreResult(0.0, 0.5, 0.5, 0.0, results)
    if not active_weights and total_w <= 0:
        return ScoreResult(0.0, 0.5, 0.5, 0.0, results)

    if active_weights:
        # ML 模式：S = Σ w·f + bias，k=1（逻辑回归形式）
        S = sum(w * r.score for _, r, w in results) + float(active_weights.get("bias", 0.0))
        k = float(active_weights.get("k", 1.0))
    else:
        # 规则模式：归一化加权 + Sigmoid
        S = sum(w * r.score for _, r, w in results) / total_w
        k = float(config.get("k", 2.5))

    prob_up = 1.0 / (1.0 + math.exp(-k * S))
    if calibrator is not None:
        try:
            prob_up = float(calibrator.calibrate([prob_up])[0])
            prob_up = max(0.001, min(0.999, prob_up))
        except Exception:  # noqa: BLE001 校准失败回退原始概率
            pass
    # 置信度归一化：ML 模式权重有正有负，用 |w| 之和归一，避免 total_w<=0 失真
    norm_w = sum(abs(w) for _, r, w in results)
    confidence = (sum(w * r.confidence for _, r, w in results) / norm_w) if norm_w > 0 else 0.0

    return ScoreResult(
        S=round(S, 4),
        prob_up=round(prob_up, 4),
        prob_down=round(1 - prob_up, 4),
        confidence=round(confidence, 4),
        factors=results,
    )


def _load_active_model():
    """加载生效的 ML 模型（权重 + 校准器）；无则返回 ({}, None)。

    环境变量 GHGW_DISABLE_ML=1 时强制禁用（供测试隔离，避免生效模型污染单测）。
    """
    import os
    if os.environ.get("GHGW_DISABLE_ML") == "1":
        return {}, None
    try:
        from model_store import load_active_weights, load_active_calibrator
        return load_active_weights(), load_active_calibrator()
    except Exception:  # noqa: BLE001 模型目录异常不影响规则引擎
        return {}, None
