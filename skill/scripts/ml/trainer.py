"""训练流程：特征构建、时间序列切分、模型训练、校准（方案 §4.9）。

防数据泄漏硬约束：
- 每个样本的因子计算窗口严格截至样本日 T；
- 大盘/基准数据同样截至 T；
- 训练/验证按时间顺序切分，禁止随机打乱。
"""
import math

import numpy as np
import pandas as pd

from factors.base import FactorContext
from scoring import compute_score
from ml.models import create_model
from ml.calibrator import ProbabilityCalibrator
from utils import get_logger

logger = get_logger("trainer")


def build_dataset(fetcher, config, scopes="industry", max_symbols=25, step=5, lookahead=5):
    """用实盘行业历史行情构建 特征矩阵（因子得分）+ 标签（未来 lookahead 日涨跌方向）。"""
    market = fetcher.get_index_history("sh000001")
    mkt_dates = market["date"] if market is not None else None  # pandas Series，searchsorted 兼容 Timestamp
    rows = []
    snap = fetcher.get_industry_snapshot()
    if snap is None or snap.empty:
        return pd.DataFrame()
    names = [str(x) for x in snap["板块名称"].tolist()[:max_symbols]]
    for name in names:
        try:
            hist = fetcher.get_industry_history(name)
            if hist is None or len(hist) < 300:
                continue
            df = hist.reset_index(drop=True)
            for i in range(250, len(df) - lookahead, step):
                window = df.iloc[: i + 1]                      # 截至 T，无未来
                d = df.iloc[i]["date"]
                if mkt_dates is not None:
                    pos = int(mkt_dates.searchsorted(d, side="right"))
                    mkt_win = market.iloc[:pos]
                else:
                    mkt_win = None
                ctx = FactorContext(mode="close", ohlcv=window, market=mkt_win)
                res = compute_score(ctx, config, scopes=scopes)
                feat = {"date": d}
                for fn, fr, _ in res.factors:
                    feat[fn] = fr.score
                feat["label"] = 1 if float(df.iloc[i + lookahead]["close"]) > float(df.iloc[i]["close"]) else 0
                rows.append(feat)
        except Exception as e:  # noqa: BLE001 单行业失败跳过，不影响整体训练
            logger.warning("行业 %s 数据获取失败，跳过: %s", name, e)
            continue
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("date").reset_index(drop=True)
    return out


def time_split(df, valid_ratio=0.2):
    """时间序列切分（不打乱）：前 (1-ratio) 训练，后 ratio 验证。"""
    split = int(len(df) * (1 - valid_ratio))
    return df.iloc[:split], df.iloc[split:]


def rule_accuracy(df, config, scopes="industry"):
    """用默认规则权重在样本上计算方向准确率（旧基线）。"""
    from scoring import load_factor_entries
    entries = load_factor_entries(config, scopes)
    k = float(config.get("k", 2.5))
    correct = 0
    total = 0
    for _, row in df.iterrows():
        S = sum(float(fc.get("weight", 0.0)) * float(row.get(name, 0.0) or 0.0)
                for name, fc in entries)
        prob = 1.0 / (1.0 + math.exp(-k * S))
        pred = 1 if prob > 0.5 else 0
        correct += int(pred == int(row["label"]))
        total += 1
    return correct / total if total else 0.0


def train_pipeline(train_df, valid_df, config, model_name="logistic", method="isotonic", seed=42):
    """完整训练：模型 + 校准 + 权重提取。返回 (weights_dict, calibrator, metrics)。"""
    features = [c for c in train_df.columns if c not in ("date", "label")]
    X_train = train_df[features].to_numpy(dtype=float)
    y_train = train_df["label"].to_numpy(dtype=int)
    X_valid = valid_df[features].to_numpy(dtype=float)
    y_valid = valid_df["label"].to_numpy(dtype=int)

    model = create_model(model_name, seed=seed)
    model.fit(X_train, y_train)

    valid_preds = model.predict_proba(X_valid)

    calibrator = ProbabilityCalibrator(method=method)
    try:
        calibrator.fit(valid_preds, y_valid)
    except Exception as e:  # noqa: BLE001 校准失败则跳过，不影响权重生效
        logger.warning("概率校准失败，跳过: %s", e)
        calibrator = None

    cal_preds = calibrator.calibrate(valid_preds) if calibrator else valid_preds
    valid_acc = float(np.mean((np.asarray(cal_preds) > 0.5) == y_valid))

    weights = model.feature_weights(features)
    bias = model.bias()

    # 系数归一化后必须同步缩放 bias，否则 S = Σw·f + bias 由 bias 主导，
    # 所有样本概率挤成常数（区分度≈0）。用 k = Σ|coef| 恢复原始 logit：
    #   k * (Σ w·f + bias/k) = Σ coef·f + bias  与原逻辑回归完全等价。
    if model_name == "logistic" and hasattr(model, "raw_coef"):
        A = float(np.sum(np.abs(np.asarray(model.raw_coef(), dtype=float)))) or 1.0
        weights = {"weights": weights, "bias": bias / A, "k": A}
    else:
        weights = {"weights": weights, "bias": bias, "k": 1.0}

    metrics = {
        "model": model_name,
        "n_train": len(train_df),
        "n_valid": len(valid_df),
        "valid_acc": round(valid_acc, 4),
        "features": features,
    }
    return weights, calibrator, metrics
