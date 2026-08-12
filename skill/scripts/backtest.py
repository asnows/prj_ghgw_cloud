"""F3 回测模块：CLI 入口 + 回测报告格式化（方案 §6.3）。"""
import re
from datetime import datetime

from data_fetcher import DataFetcher
from utils import get_logger, pct

from backtest_engine import BacktestEngine
import report_tpl as tpl

logger = get_logger("backtest")

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _parse_backtest_input(text):
    """解析 '回测600519' / '回测贵州茅台 2024-01-01 2025-01-01' / '回测半导体行业'。"""
    t = text.replace("回测", "").strip()
    dates = _DATE_RE.findall(t)
    start = dates[0] if len(dates) >= 1 else None
    end = dates[1] if len(dates) >= 2 else None
    for d in dates:
        t = t.replace(d, "").strip()
    return t, start, end


def _match_industry(text, fetcher):
    try:
        snap = fetcher.get_industry_snapshot()
        if snap is None or snap.empty:
            return None
        for n in snap["板块名称"].astype(str).tolist():
            if n and n in text:
                return n
    except Exception as e:  # noqa: BLE001
        logger.warning("行业匹配失败: %s", e)
    return None


def run_backtest(text, config, fetcher: DataFetcher):
    """回测入口：解析 → 拉实盘数据 → 引擎 → 报告。"""
    target, start, end = _parse_backtest_input(text)
    if not target:
        return "❌ 请指定回测标的，例如：回测600519 / 回测贵州茅台 / 回测半导体行业"

    # 行业 or 个股
    industry = _match_industry(target, fetcher)
    if industry:
        hist = fetcher.get_industry_history(industry)
        scopes = "industry"
        name = industry
    else:
        try:
            symbol, name = fetcher.resolve_stock(target)
        except Exception as e:  # noqa: BLE001
            return f"❌ 未找到标的「{target}」：{e}"
        hist = fetcher.get_stock_history(symbol)
        scopes = "stock"

    if hist is None or hist.empty:
        return f"❌ 未获取到 {name} 的历史行情（实盘数据），请稍后重试。"

    engine = BacktestEngine(config, fetcher)
    try:
        result = engine.run(hist, scopes, name=name, start_date=start, end_date=end)
    except ValueError as e:
        return f"❌ 回测失败：{e}"
    except Exception as e:  # noqa: BLE001
        logger.exception("回测异常")
        return f"❌ 回测失败：{e}"

    return _format_report(name, scopes, start, end, result, config)


def _format_report(name, scopes, start, end, result, config):
    m = result.metrics
    curve = result.equity_curve
    bt_cfg = config.get("backtest", {})
    buy_th = config.get("buy_threshold", 0.60)
    sell_th = config.get("sell_threshold", 0.40)

    start_d = str(curve.iloc[0]["date"].date())
    end_d = str(curve.iloc[-1]["date"].date())
    scope_label = "行业指数" if scopes == "industry" else "个股"
    meta = (f"{name}（{scope_label}）｜策略：股海怪物概率信号"
            f"（P≥{buy_th:.0%}买入 / P≤{sell_th:.0%}卖出）"
            f"｜{start_d} ~ {end_d}（{m['trading_days']} 个交易日）")

    lines = [tpl.header("回测报告", meta)]

    lines.append(tpl.section("📈 绩效总览"))
    lines.append("| 指标 | 模型策略 | 买入持有 |")
    lines.append("|------|----------|----------|")
    lines.append(f"| 累计收益率 | {pct(m['total_return'])} | {pct(m['buy_hold_return'])} |")
    lines.append(f"| 年化收益率 | {pct(m['annual_return'])} | {pct(m['buy_hold_return'] * 252 / max(m['trading_days'], 1))} |")
    lines.append(f"| 最大回撤 | {pct(m['max_drawdown'])} | {pct(m['buy_hold_max_drawdown'])} |")
    lines.append(f"| 夏普比率 | {m['sharpe']:.2f} | — |")

    lines.append(tpl.section("🎯 交易统计"))
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 总交易次数 | {m['trade_count']} 笔 |")
    if m["trade_count"]:
        lines.append(f"| 胜率 | {pct(m['win_rate'])}（{int(m['win_rate'] * m['trade_count'])}/{m['trade_count']}） |")
    else:
        lines.append("| 胜率 | — |")
    lines.append(f"| 盈亏比 | {m['profit_loss_ratio']:.2f} |")
    lines.append(f"| 平均持仓天数 | {m['avg_holding_days']:.1f} 天 |")
    lines.append(f"| 单笔最大盈利 / 最大亏损 | {pct(m['max_win'])} / {pct(m['max_loss'])} |")

    lines.append(tpl.section("📅 月度收益采样"))
    lines.append("| 月份 | 策略收益 | 买入持有 |")
    lines.append("|------|----------|----------|")
    lines += _monthly_sample(curve, result)

    lines.append(tpl.section("🕐 最近 10 笔交易"))
    lines.append("| 日期 | 方向 | 价格 | 盈亏 |")
    lines.append("|------|------|------|------|")
    for tr in result.trades[-10:]:
        lines.append(f"| {tr.entry_date} | 买入 | {tr.entry_price:,.2f} | — |")
        lines.append(f"| {tr.exit_date} | 卖出 | {tr.exit_price:,.2f} | {pct(tr.pnl_pct)} |")

    lines.append(tpl.section("⚙️ 参数说明"))
    lines.append(f"佣金 {pct(bt_cfg.get('commission', 0.00025), 3)}双边 + 印花税 {pct(bt_cfg.get('stamp_tax', 0.001))}卖出"
                 f" + 滑点 {pct(bt_cfg.get('slippage', 0.001))}；数据：东方财富/新浪实盘历史行情（前复权 qfq，多源自动降级）；"
                 "信号基于滚动窗口计算，T+1 日开盘成交，无未来函数。")
    lines.append("")
    lines.append(tpl.footer())
    return "\n".join(lines)


def _monthly_sample(curve, result):
    """月度收益采样：按净值月末值计算。"""
    df = curve.copy()
    df["ym"] = df["date"].dt.to_period("M")
    rows = []
    prev = None
    for ym, g in df.groupby("ym"):
        last_equity = g["equity"].iloc[-1]
        if prev is None:
            rows.append((str(ym), None))
        else:
            rows.append((str(ym), last_equity / prev - 1))
        prev = last_equity
    # 买入持有对应月份收益简化：用策略净值代表区间，不做独立计算
    out = []
    for ym, r in rows[-6:]:
        out.append(f"| {ym} | {pct(r) if r is not None else '—'} | — |")
    return out
