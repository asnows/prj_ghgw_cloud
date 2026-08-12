"""模型封装：逻辑回归（默认，系数=权重）与 LightGBM（可选）。"""
import numpy as np


class LogisticModel:
    """逻辑回归：标准化后系数即因子权重，可解释性最强（方案 §4.9）。"""

    name = "logistic"

    def __init__(self, seed=42, C=0.5):
        from sklearn.linear_model import LogisticRegression
        self.clf = LogisticRegression(max_iter=2000, C=C, random_state=seed)
        self._coef = None
        self._bias = None

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        self.clf.fit(X, y)
        self._coef = np.asarray(self.clf.coef_[0], dtype=float)
        self._bias = float(self.clf.intercept_[0])
        return self

    def predict_proba(self, X):
        return self.clf.predict_proba(np.asarray(X, dtype=float))[:, 1]

    def feature_weights(self, feature_names):
        """归一化系数 -> 权重表（Σ|w| 归一化后按符号保留）。"""
        w = dict(zip(feature_names, self._coef.tolist()))
        total = sum(abs(v) for v in w.values()) or 1.0
        norm = {k: v / total for k, v in w.items()}
        return norm

    def raw_coef(self):
        """返回未归一化原始系数（用于与 bias 匹配的缩放）。"""
        return self._coef

    def bias(self):
        return self._bias


class LightGBMModel:
    """LightGBM：非线性增强（需 pip install lightgbm）。"""

    name = "lightgbm"

    def __init__(self, seed=42):
        import lightgbm as lgb
        self.clf = lgb.LGBMClassifier(
            n_estimators=200, learning_rate=0.05, num_leaves=15,
            min_child_samples=20, random_state=seed, verbose=-1,
        )

    def fit(self, X, y):
        self.clf.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X):
        return self.clf.predict_proba(np.asarray(X, dtype=float))[:, 1]

    def feature_weights(self, feature_names):
        """特征重要性归一化（仅保留方向信息时权重取重要性占比，符号由系数相关性近似）。"""
        imp = self.clf.feature_importances_.astype(float)
        total = imp.sum() or 1.0
        norm = {k: v / total for k, v in zip(feature_names, imp.tolist())}
        return norm

    def bias(self):
        return 0.0


def create_model(name="logistic", seed=42):
    name = (name or "logistic").lower()
    if name == "lightgbm":
        return LightGBMModel(seed=seed)
    return LogisticModel(seed=seed)
