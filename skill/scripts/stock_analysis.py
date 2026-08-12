"""F2 个股分析：涨跌概率 + 因子明细 + 行业传导（统一报告模板）。"""
import pandas as pd

from data_fetcher import DataFetcher
from factors.base import FactorContext
from scoring import compute_score
from utils import get_logger, mode_of, now_str, pct, suggestion_of, status_label, chg_arrow
import report_tpl as tpl

logger = get_logger("stock")


class StockAnalyzer:
    """个股分析器。"""

    def __init__(self, config, fetcher: DataFetcher):
        self.config = config
        self.fetcher = fetcher

    def _mode(self):
        return mode_of(is_trading_day=self.fetcher.is_trading_day())

    def _fund_flow_of(self, symbol):
        """从资金流排行中提取主力净流入占比。"""
        try:
            rank = self.fetcher.get_fund_flow_rank(indicator="今日")
            row = rank[rank["代码"] == symbol]
            if row.empty:
                return None
            ratio = row.iloc[0].get("今日主力净流入-净占比", None)
            try:
                ratio = float(ratio)
                return {"main_net_ratio": ratio} if ratio == ratio else None
            except (TypeError, ValueError):
                return None
        except Exception as e:  # noqa: BLE001
            logger.warning("资金流获取失败 %s: %s", symbol, e)
            return None

    def _industry_prob(self, industry):
        """计算所属行业指数概率（供行业传导）。"""
        try:
            snap = self.fetcher.get_industry_snapshot()
            row = snap[snap["板块名称"] == industry]
            if row.empty:
                return None
            hist = self.fetcher.get_industry_history(industry)
            if hist is None or hist.empty:
                return None
            market = self.fetcher.get_index_history("sh000001")
            snapshot = {
                "pct_chg": _f(row.iloc[0].get("涨跌幅", 0)),
                "turnover": _f(row.iloc[0].get("换手率", 0)),
            }
            ctx = FactorContext(mode=self._mode(), ohlcv=hist, snapshot=snapshot, market=market)
            return compute_score(ctx, self.config, scopes="industry").prob_up
        except Exception as e:  # noqa: BLE001
            logger.warning("行业 %s 概率计算失败: %s", industry, e)
            return None

    def analyze(self, text):
        """解析输入并输出个股分析报告。"""
        symbol, name = self.fetcher.resolve_stock(text)
        hist = self.fetcher.get_stock_history(symbol)
        if hist is None or hist.empty:
            return f"❌ 未获取到 {name}（{symbol}）的历史行情，请检查代码或稍后重试。"

        snapshot = self._get_snapshot(symbol)

        market = self.fetcher.get_index_history("sh000001")
        fund_flow = self._fund_flow_of(symbol)

        ctx = FactorContext(mode=self._mode(), ohlcv=hist, snapshot=snapshot,
                            fund_flow=fund_flow, market=market)
        res = compute_score(ctx, self.config, scopes="stock")

        # ---- 行业传导 ----
        industry = self.fetcher.get_stock_industry(symbol)
        ind_prob = self._industry_prob(industry) if industry else None
        final_prob = res.prob_up
        conduction = None
        if ind_prob is not None:
            w = self.config.get("industry_conduction", {})
            self_w = float(w.get("self_weight", 0.7))
            ind_w = float(w.get("industry_weight", 0.3))
            final_prob = round(self_w * res.prob_up + ind_w * ind_prob, 4)
            conduction = ind_prob

        return self._format_report(name, symbol, industry, snapshot, res,
                                   final_prob, conduction)

    def _get_snapshot(self, symbol):
        """获取个股实时快照：优先东财全市场快照，失败降级腾讯单股接口。"""
        try:
            spot = self.fetcher.get_stock_spot()
            if spot is not None and not spot.empty:
                row = spot[spot["代码"] == symbol]
                if not row.empty:
                    r = row.iloc[0]
                    return {
                        "price": _f(r.get("最新价", 0)),
                        "pct_chg": _f(r.get("涨跌幅", 0)),
                        "turnover": _f(r.get("换手率", 0)),
                        "volume_ratio": _f(r.get("量比", 0)),
                    }
        except Exception as e:  # noqa: BLE001 东财快照不可达
            logger.warning("东财个股快照不可用，降级腾讯行情: %s", e)
        try:
            q = self.fetcher.get_stock_quote(symbol)
            return {
                "price": q.get("price"),
                "pct_chg": q.get("pct_chg"),
                "turnover": q.get("turnover"),
                "volume_ratio": q.get("volume_ratio"),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("腾讯行情也失败，使用历史数据兜底: %s", e)
            return None

    def _format_report(self, name, symbol, industry, snapshot, res, final_prob, conduction):
        mode = self._mode()
        level, tip = suggestion_of(final_prob)
        conf_label = "高" if res.confidence >= 0.8 else "中" if res.confidence >= 0.5 else "低"
        meta = (f"{now_str()}｜{'盘中实时' if mode == 'intraday' else '收盘'}"
                f"｜所属行业：{industry or '未知'}")
        status = status_label(final_prob)

        lines = [tpl.header("个股涨跌概率分析", meta)]

        # ---- 区域一：标的信息区 ----
        lines.append(tpl.section("📌 标的"))
        lines.append(f"{name}  {symbol}")

        # ---- 区域三（文本版）：行情与概率数据区（表格化，终端/HTML 双端整洁） ----
        lines.append(tpl.section("📊 行情与概率"))
        chg = snapshot.get("pct_chg")
        buy_label = "🟢 高" if final_prob >= 0.70 else ("⚪ 低" if final_prob < 0.30 else "🟡 中")
        sell_label = "🔴 高" if 1 - final_prob >= 0.70 else ("⚪ 低" if 1 - final_prob < 0.30 else "🟡 中")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 最新价 | {_fmt_price(snapshot.get('price'))} |")
        lines.append(f"| 涨跌幅 | {_fmt_chg(chg)} {chg_arrow(chg)} |")
        lines.append(f"| 买入概率 | {pct(final_prob)}（{buy_label}） |")
        lines.append(f"| 卖出概率 | {pct(1 - final_prob)}（{sell_label}） |")
        lines.append(f"| 状态 | {status} ｜ {level}（{tip}） |")
        lines.append(f"| 置信度 | {conf_label} |")

        # ---- 区域四：因子明细（信息全面性保留） ----
        lines.append(tpl.section("📊 因子明细"))
        lines.append("| 因子 | 得分 | 说明 |")
        lines.append("|------|------|------|")
        for fname, fr, w in res.factors:
            lines.append(f"| {fname} | {fr.score:+.2f} | {fr.detail} |")

        if conduction is not None:
            delta = final_prob - res.prob_up
            direction = "正向加成" if delta >= 0 else "负向拖累"
            lines.append(f"| 行业传导 | {delta:+.2f} | 所属{industry}上涨概率 {pct(conduction)}，{direction} |")

        if res.confidence < 0.5:
            lines.append("")
            lines.append("⚠️ 当前信号稳定性不足，建议降低仓位或观望。")
        lines.append("")
        lines.append(tpl.footer())
        return "\n".join(lines)


def _f(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _fmt_price(v):
    return "—" if v is None else f"{v:,.2f}"


def _fmt_chg(v, show_plus=True):
    if v is None:
        return "—"
    return f"{v:+.2f}%" if show_plus else f"{v:.2f}%"
