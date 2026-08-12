"""技术指标计算（pandas 向量化实现）。

所有函数输入为 pd.Series / pd.DataFrame，输出与输入索引对齐，
NaN 表示数据不足，由上层按置信度处理。
"""
import numpy as np
import pandas as pd


def ma(series, n):
    return series.rolling(n).mean()


def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()


def rsi(close, period=14):
    diff = close.diff()
    up = diff.clip(lower=0).rolling(period).mean()
    down = (-diff.clip(upper=0)).rolling(period).mean()
    # down==0（持续上涨）→ RS=∞ → RSI=100；up==down==0（数据不足期）→ 50
    rs = up / down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.fillna(100.0)
    out = out.mask((up == 0) & (down == 0), 50.0)
    return out


def macd(close, fast=12, slow=26, signal=9):
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist


def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def boll(close, n=20, k=2.0):
    mid = ma(close, n)
    std = close.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def volume_ratio(volume, window=5):
    avg = volume.rolling(window).mean()
    return volume / avg.replace(0, np.nan)


def returns(series, n):
    return series.pct_change(n)


def consecutive_days(close):
    """连续同向涨跌天数（带方向）：连涨为正，连跌为负。"""
    chg = close.diff().fillna(0.0)
    sign = np.sign(chg)
    out = np.zeros(len(close))
    cnt = 0
    prev = 0
    for i, s in enumerate(sign):
        if s == 0:
            out[i] = cnt
        elif s == prev:
            cnt += s
            out[i] = cnt
        else:
            cnt = s
            prev = s
            out[i] = cnt
    return pd.Series(out, index=close.index)


def linear_score(x, lo, hi):
    """把 x 从 [lo, hi] 线性映射到 [-1, 1]，越界截断。"""
    if hi <= lo:
        return 0.0
    return float(np.clip((x - lo) / (hi - lo) * 2 - 1, -1, 1))
