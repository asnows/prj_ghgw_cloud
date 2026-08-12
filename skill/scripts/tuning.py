"""F4 调优入口：训练、调优报告、版本管理与回滚（统一报告模板）。"""
from datetime import datetime

from ml.trainer import build_dataset, time_split, rule_accuracy, train_pipeline
from ml.explainer import explain_weights
from model_store import load_active_meta, next_version, save_version, rollback
from scoring import load_factor_entries
from utils import get_logger, pct, _now
import report_tpl as tpl

logger = get_logger("tuning")


def _default_weights(config, scopes="industry"):
    """当前默认（规则）权重表。"""
    return {name: float(fc.get("weight", 0.0)) for name, fc in load_factor_entries(config, scopes)}


def _discrimination_metrics(valid_df, weights, calibrator):
    """新权重在验证集上的概率区分度：标准差 + 偏离 0.5 的样本占比。

    防止"准确率勉强达标但概率全挤在 0.5 附近"的无信息模型上线。
    """
    import math

    import numpy as np

    features = [c for c in valid_df.columns if c not in ("date", "label")]
    w = weights["weights"]
    bias = float(weights.get("bias", 0.0))
    k = float(weights.get("k", 1.0))
    probs = []
    for _, row in valid_df.iterrows():
        S = bias + sum(float(w.get(name, 0.0) or 0.0) * float(row.get(name, 0.0) or 0.0)
                       for name in features)
        p = 1.0 / (1.0 + math.exp(-k * S))
        probs.append(p)
    if calibrator is not None:
        try:
            probs = list(calibrator.calibrate(probs))
        except Exception:  # noqa: BLE001 校准失败用原始概率
            pass
    arr = np.asarray(probs, dtype=float)
    std = float(arr.std()) if len(arr) > 1 else 0.0
    far = float(np.mean(np.abs(arr - 0.5) > 0.05))
    return std, far


def run_tuning(config, fetcher, text="调优模型"):
    """调优入口。"""
    mt = config.get("ml_tuning", {})
    if not mt.get("enabled", True):
        return "❌ ML 调优已关闭（config.yaml ml_tuning.enabled=false）"

    if "回滚" in text:
        v = rollback()
        return f"🔄 已回滚到 v{v}。" if v else "❌ 无更早版本可回滚。"

    model_name = mt.get("model", "logistic")
    min_samples = int(mt.get("min_samples", 300))
    apply_threshold = float(mt.get("apply_threshold", 0.0))
    seed = int(mt.get("random_state", 42))
    scopes = "industry"

    logger.info("构建训练数据集（实盘行业历史行情）...")
    df = build_dataset(fetcher, config, scopes=scopes, step=5, lookahead=5)
    if df.empty:
        return "❌ 训练数据为空，请检查网络与数据接口。"
    if len(df) < min_samples:
        return (f"❌ 训练样本不足：当前 {len(df)} 条，需要 ≥ {min_samples} 条。"
                "请积累更多实盘历史数据后再调优。")

    train_df, valid_df = time_split(df, valid_ratio=0.2)
    old_acc = rule_accuracy(valid_df, config, scopes=scopes)
    weights, calibrator, metrics = train_pipeline(
        train_df, valid_df, config, model_name=model_name, seed=seed)
    new_acc = metrics["valid_acc"]

    date_range = f"{train_df['date'].min().date()} ~ {valid_df['date'].max().date()}"

    # ---- 区分度检查：低区分度模型（概率全挤在 0.5 附近）即使准确率达标也拒绝 ----
    prob_std, far_ratio = _discrimination_metrics(valid_df, weights, calibrator)
    min_std = float(mt.get("min_prob_std", 0.05))
    min_far = float(mt.get("min_far_ratio", 0.10))
    discrim_ok = prob_std >= min_std and far_ratio >= min_far

    # ---- 生效门槛：样本外准确率 ≥ 旧基线 + apply_threshold，且区分度达标 ----
    if new_acc < old_acc + apply_threshold or not discrim_ok:
        reasons = []
        if new_acc < old_acc + apply_threshold:
            reasons.append(f"准确率 {pct(new_acc)} < 基线 {pct(old_acc)} + {pct(apply_threshold)}")
        if not discrim_ok:
            reasons.append(f"区分度不足（概率标准差 {prob_std:.3f}，偏离 0.5 样本占比 {pct(far_ratio)}）")
        meta = f"样本 {len(df)} 条（{date_range}）｜时间序列 80%/20%｜模型：{model_name}"
        lines = [tpl.header("模型调优报告", meta)]
        lines.append(tpl.section("📈 样本外表现"))
        lines.append("| 指标 | 旧权重（规则基线） | 新权重（待评估） |")
        lines.append("|------|------------------|------------------|")
        lines.append(f"| 整体准确率 | {pct(old_acc)} | {pct(new_acc)} |")
        lines.append("")
        lines.append("❌ 未达标（" + "；".join(reasons) + "），已拒绝更新，当前生效版本不变。")
        lines.append("")
        lines.append(tpl.footer())
        return "\n".join(lines)

    # ---- 达标：保存新版本 ----
    meta = {
        "trained_at": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "scopes": scopes,
        "model": model_name,
        "n_samples": len(df),
        "old_acc": round(old_acc, 4),
        "valid_acc": new_acc,
    }
    v = save_version(weights, calibrator, meta)

    default_w = _default_weights(config, scopes)
    explain_rows = explain_weights(weights["weights"], default_w)
    buy_th = config.get("buy_threshold", 0.60)
    sell_th = config.get("sell_threshold", 0.40)
    meta = f"样本 {len(df)} 条（{date_range}）｜时间序列 80%/20%（未随机打乱）｜模型：{model_name}"

    lines = [tpl.header("模型调优报告", meta)]

    lines.append(tpl.section("📈 样本外表现"))
    lines.append("| 指标 | 旧权重（规则基线） | 新权重（v%d） | 变化 |" % v)
    lines.append("|------|------------------|---------------|------|")
    lines.append(f"| 整体准确率 | {pct(old_acc)} | {pct(new_acc)} | {pct(new_acc - old_acc, 2)} |")

    lines.append(tpl.section("⚖️ 权重调整（模型系数归一化）"))
    lines.append("| 因子 | 旧权重 | 新权重 | 变化 |")
    lines.append("|------|--------|--------|------|")
    for r in explain_rows:
        old = f"{r['old_weight']:.2f}" if r["old_weight"] is not None else "—"
        delta = f"{r['delta']:+.2f}" if r["delta"] is not None else "—"
        lines.append(f"| {r['factor']} | {old} | {r['new_weight']:.2f} | {delta} |")

    lines.append(tpl.section("🎯 校准与阈值"))
    lines.append(f"概率校准：Isotonic（已应用）｜ 买卖阈值沿用 config（买入 {buy_th:.0%} / 卖出 {sell_th:.0%}）")
    lines.append("")
    lines.append(f"🔄 版本：v{v} 已生效（历史版本可一键回滚）")
    lines.append("")
    lines.append(tpl.footer())
    return "\n".join(lines)
