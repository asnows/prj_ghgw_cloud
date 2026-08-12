"""因子插件抽象基类与统一数据结构。

新增因子的约定（方案 §4.1）：
1. 在 factors/ 目录新建 xxx_factor.py，继承 BaseFactor 并用 @register 装饰；
2. 在 config/config.yaml 的 factors 表登记 name/weight/enabled/scopes/params；
3. 无需改动主流程，__init__.py 自动扫描注册。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class FactorContext:
    """统一数据上下文：各因子只从上下文中取所需数据。"""
    mode: str = "close"                       # "intraday" 盘中实时 / "close" 收盘
    ohlcv: Optional[pd.DataFrame] = None      # 标的历史行情（标准列：date/open/high/low/close/volume/amount/pct_chg）
    snapshot: Optional[dict] = None           # 实时快照（最新价/涨跌幅/量比/换手率）
    fund_flow: Optional[dict] = None          # 资金流（个股：main_net_ratio 主力净占比等）
    market: Optional[pd.DataFrame] = None     # 大盘指数行情（市场环境因子）
    benchmark: Optional[pd.DataFrame] = None  # 基准指数行情（相对强弱因子，指数场景）
    config: dict = field(default_factory=dict)  # 该因子专属 params


@dataclass
class FactorResult:
    """统一因子输出：得分 + 解释 + 置信度。"""
    score: float = 0.0
    detail: str = ""
    confidence: float = 1.0


# ---- 注册表 ----
_REGISTRY = {}


def register(cls):
    """类装饰器：注册因子（由 factors/__init__.py 扫描触发）。"""
    if not cls.name:
        raise ValueError(f"因子 {cls.__name__} 缺少 name")
    _REGISTRY[cls.name] = cls
    return cls


def get_factor_classes():
    """返回 {name: class} 注册表。"""
    return _REGISTRY


class BaseFactor(ABC):
    name: str = ""
    scopes: list = ["both"]   # both=行业+个股 / stock=个股专属 / index=三大指数
    weight: float = 0.0       # 默认权重（可被 config 覆盖）

    @abstractmethod
    def compute(self, ctx: FactorContext) -> FactorResult:
        """输入统一上下文，输出 FactorResult（score ∈ [-1,1]）。"""
        raise NotImplementedError

    @staticmethod
    def _latest(series, default=0.0):
        """取序列最后一个有效值，空则返回 default。"""
        v = series.dropna()
        return float(v.iloc[-1]) if len(v) else default
