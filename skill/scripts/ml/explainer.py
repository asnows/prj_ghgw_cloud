"""特征归因：将模型权重/重要性解释到因子层，维持可解释性（方案 §4.9）。"""


def explain_weights(feature_weights, old_weights=None):
    """生成权重归因明细：因子、新权重、变化。"""
    rows = []
    all_names = sorted(set(feature_weights) | set(old_weights or {}))
    for name in all_names:
        new_w = feature_weights.get(name, 0.0)
        old_w = (old_weights or {}).get(name, None)
        rows.append({
            "factor": name,
            "new_weight": new_w,
            "old_weight": old_w,
            "delta": (new_w - old_w) if old_w is not None else None,
        })
    return rows


def explain_prediction(feature_weights, feature_values):
    """单样本归因：各因子对综合得分的贡献。"""
    rows = []
    for name, w in feature_weights.items():
        v = feature_values.get(name, 0.0)
        rows.append({"factor": name, "weight": w, "value": v, "contribution": w * v})
    return rows
