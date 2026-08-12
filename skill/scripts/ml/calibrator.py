"""概率校准：Platt Scaling / Isotonic Regression（方案 §4.9 校准层）。"""
import pickle


class ProbabilityCalibrator:
    """将模型原始概率校准为贴近真实频率的概率。"""

    def __init__(self, method="isotonic"):
        self.method = method
        self.model = None

    def fit(self, preds, y, min_levels=5):
        preds = list(preds)
        y = list(y)
        if self.method == "platt":
            from sklearn.linear_model import LogisticRegression
            import numpy as np
            self.model = LogisticRegression(max_iter=2000)
            X = np.asarray(preds, dtype=float).reshape(-1, 1)
            self.model.fit(X, np.asarray(y, dtype=int))
        else:  # isotonic（默认，无需分布假设）
            from sklearn.isotonic import IsotonicRegression
            self.model = IsotonicRegression(out_of_bounds="clip")
            self.model.fit(preds, y)
            # 退化检测：保序回归在样本少/概率分布集中时会退化成极少数
            # 常数档位（阶梯状），映射后概率几乎无区分度。档位过少则
            # 自动回退为 Platt Scaling（平滑连续映射）。
            levels = set(round(float(x), 4) for x in self.model.predict(list(set(preds))))
            if len(levels) < min_levels:
                from sklearn.linear_model import LogisticRegression
                import numpy as np
                self.model = LogisticRegression(max_iter=2000)
                X = np.asarray(preds, dtype=float).reshape(-1, 1)
                self.model.fit(X, np.asarray(y, dtype=int))
                self.method = "platt(fallback)"
        return self

    def calibrate(self, preds):
        if self.model is None:
            return list(preds)
        preds = list(preds)
        if self.method == "platt" or self.method == "platt(fallback)":
            # Platt（LogisticRegression）要求 2D 输入，且应返回概率而非类别标签
            import numpy as np
            X = np.asarray(preds, dtype=float).reshape(-1, 1)
            return list(self.model.predict_proba(X)[:, 1])
        return list(self.model.predict(preds))

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path):
        with open(path, "rb") as f:
            return pickle.load(f)
