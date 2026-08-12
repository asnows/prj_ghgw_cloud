"""F1 行业分析：三大指数涨跌概率 + 看涨/看跌 Top10（方案 §6.1，统一报告模板）。"""
from concurrent.futures import ThreadPoolExecutor

from data_fetcher import DataFetcher
from factors.base import FactorContext
from scoring import compute_score
from utils import (get_logger, mode_of, now_str, pct, suggestion_of,
                   status_label, chg_arrow, data_basis, basis_label)
import report_tpl as tpl

logger = get_logger("industry")


class IndustryAnalyzer:
    """行业与大盘指数分析器。"""

    def __init__(self, config, fetcher: DataFetcher):
        self.config = config
        self.fetcher = fetcher
        self.out_cfg = config.get("output", {})
        self.prev_date = None  # 回退基准日期（上一交易日收盘），由 analyze 时记录

    def _mode(self):
        return mode_of(is_trading_day=self.fetcher.is_trading_day())

    def _basis(self):
        """四段式数据基准（盘前/非交易日 → 上一交易日收盘）。"""
        return data_basis(is_trading_day=self.fetcher.is_trading_day())

    @staticmethod
    def _last_close(hist):
        """历史日线最后一根 K 线：{date, close, pct_chg}。
        涨跌幅由最后两根 K 线收盘价计算（百分数，与快照"涨跌幅"列单位一致）。
        """
        if hist is None or hist.empty:
            return None
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else None
        close = _f(last.get("close"))
        pct_chg = None
        if close is not None and prev is not None:
            prev_close = _f(prev.get("close"))
            if prev_close:
                pct_chg = round((close - prev_close) / prev_close * 100, 4)
        return {"date": last.get("date"), "close": close, "pct_chg": pct_chg}

    # ---------- 三大指数 ----------
    def analyze_indices(self):
        mode = self._mode()
        basis = self._basis()
        snap = self.fetcher.get_index_snapshot()
        bench = None
        out = []
        for idx in self.config.get("data", {}).get("indices", []):
            name, symbol = idx["name"], idx["symbol"]
            try:
                hist = self.fetcher.get_index_history(symbol)
                if hist is None or hist.empty:
                    continue
                if bench is None:
                    bench = self.fetcher.get_index_history("sh000001")
                snapshot = {}
                if basis == "prev_close":
                    # 盘前/非交易日：快照不可信，回退历史日线最后一根 K 线
                    lc = self._last_close(hist)
                    if lc:
                        snapshot = {"price": lc["close"], "pct_chg": lc["pct_chg"]}
                        if self.prev_date is None and lc.get("date") is not None:
                            self.prev_date = lc["date"].strftime("%Y-%m-%d")
                else:
                    row = snap[snap["名称"] == name] if not snap.empty else None
                    if row is not None and not row.empty:
                        r = row.iloc[0]
                        snapshot = {
                            "price": _f(r.get("price", r.get("最新价", 0))),
                            "pct_chg": _f(r.get("pct_chg", r.get("涨跌幅", 0))),
                        }
                ctx = FactorContext(mode=mode, ohlcv=hist, snapshot=snapshot, benchmark=bench)
                res = compute_score(ctx, self.config, scopes="index")
                out.append({
                    "name": name, "symbol": symbol,
                    "price": snapshot.get("price"),
                    "pct_chg": snapshot.get("pct_chg"),
                    "prob_up": res.prob_up, "prob_down": res.prob_down,
                    "S": res.S, "confidence": res.confidence,
                })
            except Exception as e:  # noqa: BLE001
                logger.warning("指数 %s 分析失败: %s", name, e)
        return out

    # ---------- 全行业 ----------
    def analyze_industries(self):
        mode = self._mode()
        basis = self._basis()
        snap = self.fetcher.get_industry_snapshot()
        if snap is None or snap.empty:
            return [], []
        market = self.fetcher.get_index_history("sh000001")
        # 盘前/非交易日快照可能出现重复行：按板块名称去重（保留首行），仅用于获取行业列表
        if basis == "prev_close" and "板块名称" in snap.columns:
            snap = snap.drop_duplicates(subset=["板块名称"])
        rows = [r for _, r in snap.iterrows()]
        results = []
        missing = []

        def work(row):
            name = str(row.get("板块名称", ""))
            try:
                hist = self.fetcher.get_industry_history(name)
                if hist is None or hist.empty:
                    missing.append(name)
                    return None
                if basis == "prev_close":
                    # 盘前/非交易日：快照价格/涨跌幅不可信，回退历史日线最后一根 K 线
                    lc = self._last_close(hist)
                    price = lc["close"] if lc else None
                    pct_chg = lc["pct_chg"] if lc else None
                    snapshot = {"pct_chg": pct_chg, "turnover": None}
                    if self.prev_date is None and lc and lc.get("date") is not None:
                        self.prev_date = lc["date"].strftime("%Y-%m-%d")
                else:
                    price = _f(row.get("最新价", 0))
                    pct_chg = _f(row.get("涨跌幅", 0))
                    snapshot = {
                        "pct_chg": pct_chg,
                        "turnover": _f(row.get("换手率", 0)),
                    }
                ctx = FactorContext(mode=mode, ohlcv=hist, snapshot=snapshot, market=market)
                res = compute_score(ctx, self.config, scopes="industry")
                return {
                    "name": name,
                    "price": price,
                    "pct_chg": pct_chg,
                    "prob_up": res.prob_up, "prob_down": res.prob_down,
                    "S": res.S, "confidence": res.confidence,
                }
            except Exception as e:  # noqa: BLE001
                missing.append(name)
                logger.warning("行业 %s 分析失败: %s", name, e)
                return None

        with ThreadPoolExecutor(max_workers=3) as ex:
            for r in ex.map(work, rows):
                if r is not None:
                    results.append(r)

        results.sort(key=lambda x: x["prob_up"], reverse=True)
        return results, missing

    def format_report(self, index_results, industry_results, missing=None):
        basis = self._basis()
        bull_top = int(self.out_cfg.get("bull_top", 10))
        bear_top = int(self.out_cfg.get("bear_top", 10))
        meta = f"{now_str()}｜{basis_label(basis, self.prev_date)}"
        total = len(industry_results)

        lines = [tpl.header("A股行业涨跌概率排行", meta)]

        # 大盘：表格（终端/HTML 双端整洁）
        lines.append(tpl.section("📌 大盘指数"))
        lines.append("| 指数 | 最新点位 | 今日涨跌 | 上涨概率 | 信号 |")
        lines.append("|------|----------|----------|----------|------|")
        for r in index_results:
            level, _ = suggestion_of(r["prob_up"])
            lines.append(
                f"| {r['name']} | {_fmt_price(r['price'])} | {_fmt_chg(r['pct_chg'])}"
                f" | {pct(r['prob_up'])} | {level} |"
            )

        # 看涨：表格
        lines.append(tpl.section(f"🟢 看涨 Top{bull_top}（全市场 {total} 个行业 · 买入概率降序）"))
        lines.append("| 排名 | 行业 | 今日涨幅 | 买入概率 | 卖出概率 |")
        lines.append("|------|------|----------|----------|----------|")
        for i, r in enumerate(industry_results[:bull_top], 1):
            icon = "🟢" if r["prob_up"] >= 0.70 else "⚪"
            lines.append(
                f"| {i} | {icon} {r['name']} | {_fmt_chg(r['pct_chg'])}"
                f" | {pct(r['prob_up'])} | {pct(r['prob_down'])} |"
            )

        # 看跌：表格
        bear = sorted(industry_results, key=lambda x: x["prob_up"])[:bear_top]
        lines.append(tpl.section(f"🔴 看跌 Top{bear_top}（卖出概率降序）"))
        lines.append("| 排名 | 行业 | 今日涨幅 | 买入概率 | 卖出概率 |")
        lines.append("|------|------|----------|----------|----------|")
        for i, r in enumerate(bear, 1):
            icon = "🔴" if r["prob_down"] >= 0.70 else "⚪"
            lines.append(
                f"| {i} | {icon} {r['name']} | {_fmt_chg(r['pct_chg'])}"
                f" | {pct(r['prob_up'])} | {pct(r['prob_down'])} |"
            )

        if missing:
            lines.append("")
            lines.append("⚠️ 数据缺失/异常：" + "、".join(missing) + "（接口异常，已跳过）")
        lines.append("")
        lines.append(tpl.footer())
        return "\n".join(lines)

    def run(self):
        """全流程：指数 + 行业 + 报告。"""
        index_results = self.analyze_indices()
        industry_results, missing = self.analyze_industries()
        return self.format_report(index_results, industry_results, missing)

    def run_single(self, industry_name):
        """指定行业：展示该行业详情 + 其在看涨/看跌榜中的位置（统一模板）。"""
        index_results = self.analyze_indices()
        results, missing = self.analyze_industries()
        hit = next((r for r in results if r["name"] == industry_name), None)
        rank = next((i for i, r in enumerate(results, 1) if r["name"] == industry_name), None)

        basis = self._basis()
        meta = f"{industry_name}｜{now_str()}｜{basis_label(basis, self.prev_date)}"
        lines = [tpl.header("行业分析", meta)]

        if hit is None:
            lines.append(f"❌ 未获取到「{industry_name}」数据，或该行业不在当前行业列表中。")
            if missing:
                lines.append("")
                lines.append("⚠️ 数据缺失/异常：" + "、".join(missing))
            lines.append("")
            lines.append(tpl.footer())
            return "\n".join(lines)

        level, tip = suggestion_of(hit["prob_up"])
        bull_top = int(self.out_cfg.get("bull_top", 10))
        bear_top = int(self.out_cfg.get("bear_top", 10))
        if rank and rank <= bull_top:
            rank_note = f"｜ 看涨榜第 {rank} 名"
        elif rank and rank > len(results) - bear_top:
            rank_note = f"｜ 看跌榜 Top{bear_top}"
        else:
            rank_note = "｜ 未入双榜"

        lines.append(tpl.section("🎯 概率信号"))
        lines.append(f"最新价：{_fmt_price(hit['price'])} ｜ 今日涨跌：{_fmt_chg(hit['pct_chg'])}{rank_note}")
        lines.append("")
        lines.append(f"上涨概率 {pct(hit['prob_up'])} ｜ 下跌概率 {pct(hit['prob_down'])} ｜ 信号：{level}（{tip}）")

        if index_results:
            lines.append(tpl.section("📌 大盘指数参考"))
            lines.append("| 指数 | 最新点位 | 今日涨跌 | 上涨概率 | 下跌概率 |")
            lines.append("|------|----------|----------|----------|----------|")
            for r in index_results:
                lines.append(f"| {r['name']} | {_fmt_price(r['price'])} | {_fmt_chg(r['pct_chg'])} | {pct(r['prob_up'])} | {pct(r['prob_down'])} |")

        if missing:
            lines.append("")
            lines.append("⚠️ 数据缺失/异常：" + "、".join(missing))
        lines.append("")
        lines.append(tpl.footer())
        return "\n".join(lines)


def _f(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN -> None
    except (TypeError, ValueError):
        return None


def _fmt_price(v):
    return "—" if v is None else f"{v:,.2f}"


def _fmt_chg(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"
