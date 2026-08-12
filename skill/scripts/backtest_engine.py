"""回测引擎（F3）：滚动信号生成、模拟交易、绩效统计。

硬约束（方案 §4.8）：
- 数据：实盘历史行情（akshare 东方财富源），严禁模拟/合成序列。
- 防未来函数：信号仅使用 T 日及之前数据，成交在 T+1 日开盘价。
- 指标严格滚动计算，禁止全样本计算后切片。
"""
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from factors.base import FactorContext
from scoring import compute_score

NO_RISK_RATE = 0.02
TRADING_DAYS = 252


@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    holding_days: int


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: list
    metrics: dict


class BacktestEngine:
    """回测引擎。"""

    def __init__(self, config, fetcher):
        self.config = config
        self.fetcher = fetcher
        self.bt = config.get("backtest", {})

    def _params(self):
        return {
            "initial_capital": float(self.bt.get("initial_capital", 1_000_000)),
            "commission": float(self.bt.get("commission", 0.00025)),
            "stamp_tax": float(self.bt.get("stamp_tax", 0.001)),
            "slippage": float(self.bt.get("slippage", 0.001)),
            "warmup": int(self.bt.get("warmup_days", 250)),
        }

    def generate_signals(self, df, scopes, start_idx):
        """滚动计算每日上涨概率（截至 T 的窗口，T+1 执行）。"""
        n = len(df)
        probs = [None] * n
        market_df = None
        if "mkt_close" in df.columns:
            market_df = df[["date", "mkt_close"]].rename(columns={"mkt_close": "close"})
        for i in range(start_idx, n):
            window = df.iloc[: i + 1]
            mkt = market_df.iloc[: i + 1] if market_df is not None else None
            ctx = FactorContext(mode="close", ohlcv=window, market=mkt)
            res = compute_score(ctx, self.config, scopes=scopes)
            probs[i] = res.prob_up
        return probs

    def run(self, hist, scopes, name="标的", start_date=None, end_date=None):
        """执行回测。hist 为实盘历史日线（标准列，升序）。"""
        p = self._params()
        warmup = p["warmup"]
        capital = p["initial_capital"]
        commission = p["commission"]
        stamp_tax = p["stamp_tax"]
        slippage = p["slippage"]
        buy_th = float(self.config.get("buy_threshold", 0.60))
        sell_th = float(self.config.get("sell_threshold", 0.40))

        df = hist.copy()
        if df is None or df.empty or len(df) < warmup + 5:
            raise ValueError(f"{name} 历史数据不足（需 ≥ {warmup + 5} 个交易日），无法回测")

        # 回测默认取尾部窗口（约 3 年），避免全量历史导致滚动计算过慢
        max_bars = int(self.bt.get("max_bars", 1000))
        if len(df) > max_bars:
            df = df.iloc[-max_bars:].reset_index(drop=True)

        # 合并大盘基准（市场环境因子输入，截至同日）
        market = self.fetcher.get_index_history("sh000001")
        if market is not None and not market.empty:
            mkt = market[["date", "close"]].rename(columns={"close": "mkt_close"})
            df = df.merge(mkt, on="date", how="left")
        df = df.reset_index(drop=True)
        n = len(df)

        # 信号（从 warmup 起）
        probs = self.generate_signals(df, scopes, start_idx=warmup)

        # 交易起始索引：max(warmup, start_date 对应索引)
        start_trade = warmup
        if start_date:
            ts = pd.Timestamp(start_date)
            idx = df.index[df["date"] >= ts]
            if len(idx):
                start_trade = max(warmup, int(idx[0]))
        trade_end = n - 1
        if end_date:
            ts = pd.Timestamp(end_date)
            idx = df.index[df["date"] <= ts]
            if len(idx):
                trade_end = min(trade_end, int(idx[-1]))
        if trade_end <= start_trade:
            raise ValueError("回测区间不足，请调整时间范围")

        # ---- 模拟交易 ----
        cash = capital
        shares = 0.0
        position = False
        entry = None
        trades = []
        equity_rows = []

        for i in range(start_trade, trade_end + 1):
            today = df.iloc[i]
            tomorrow = df.iloc[i + 1] if i + 1 < n else None
            prob = probs[i]

            if not position and prob is not None and prob >= buy_th and tomorrow is not None:
                price = float(tomorrow["open"]) * (1 + slippage)
                shares = cash / price
                cash = 0.0
                entry = {"date": str(tomorrow["date"].date()), "price": price}
                position = True
            elif position and prob is not None and prob <= sell_th and tomorrow is not None:
                price = float(tomorrow["open"]) * (1 - slippage)
                proceeds = shares * price
                cost_ratio = commission + stamp_tax
                cash = proceeds * (1 - cost_ratio)
                pnl_pct = (price * (1 - cost_ratio)) / entry["price"] - 1
                holding_days = (tomorrow["date"] - pd.Timestamp(entry["date"])).days
                trades.append(Trade(
                    entry_date=entry["date"], entry_price=round(entry["price"], 4),
                    exit_date=str(tomorrow["date"].date()), exit_price=round(price, 4),
                    pnl_pct=pnl_pct, holding_days=holding_days,
                ))
                shares = 0.0
                position = False

            close_now = float(today["close"]) if position else 0.0
            equity = cash + shares * close_now
            equity_rows.append({"date": today["date"], "equity": equity})

        # 期末按最后收盘价估值
        if position and equity_rows:
            equity_rows[-1]["equity"] = cash + shares * float(df.iloc[trade_end]["close"])

        curve = pd.DataFrame(equity_rows)
        if curve.empty:
            raise ValueError("回测区间内无交易信号，请扩大区间或调整阈值")

        # ---- 绩效统计 ----
        metrics = self._metrics(curve, trades, capital, df, start_trade, trade_end)
        return BacktestResult(equity_curve=curve, trades=trades, metrics=metrics)

    def _metrics(self, curve, trades, capital, df, start_trade, trade_end):
        equity = curve["equity"].to_numpy(dtype=float)
        final = equity[-1]
        total_return = final / capital - 1

        days = len(equity)
        annual_return = (1 + total_return) ** (TRADING_DAYS / max(days, 1)) - 1 if total_return > -1 else -1.0

        peak = np.maximum.accumulate(equity)
        dd = equity / peak - 1
        max_drawdown = float(dd.min())

        # 日收益序列（用于夏普）
        rets = np.diff(equity) / equity[:-1]
        sharpe = 0.0
        if len(rets) > 1 and rets.std() > 0:
            sharpe = (rets.mean() - NO_RISK_RATE / TRADING_DAYS) / rets.std() * math.sqrt(TRADING_DAYS)

        # 交易统计
        n_trades = len(trades)
        wins = [t for t in trades if t.pnl_pct > 0]
        losses = [t for t in trades if t.pnl_pct <= 0]
        win_rate = len(wins) / n_trades if n_trades else 0.0
        avg_win = float(np.mean([t.pnl_pct for t in wins])) if wins else 0.0
        avg_loss = float(np.mean([abs(t.pnl_pct) for t in losses])) if losses else 0.0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else (avg_win if avg_win else 0.0)
        avg_holding = float(np.mean([t.holding_days for t in trades])) if trades else 0.0
        max_win = max((t.pnl_pct for t in trades), default=0.0)
        max_loss = min((t.pnl_pct for t in trades), default=0.0)

        # 买入持有基准（同期）
        seg = df.iloc[start_trade: trade_end + 1]
        bh_start = float(seg.iloc[0]["close"])
        bh_end = float(seg.iloc[-1]["close"])
        bh_return = bh_end / bh_start - 1
        bh_close = seg["close"].to_numpy(dtype=float)
        bh_peak = np.maximum.accumulate(bh_close)
        bh_max_dd = float((bh_close / bh_peak - 1).min())

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "trade_count": n_trades,
            "avg_holding_days": avg_holding,
            "max_win": max_win,
            "max_loss": max_loss,
            "buy_hold_return": bh_return,
            "buy_hold_max_drawdown": bh_max_dd,
            "trading_days": days,
        }
