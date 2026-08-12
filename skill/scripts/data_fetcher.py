"""数据获取层：akshare 封装（实时优先）+ 缓存 + 重试 + 双模式 + 名称解析。

接口清单（与方案 §3.1 对应）：
- 实时快照：stock_board_industry_name_em / stock_zh_a_spot_em / stock_zh_index_spot_em / stock_bid_ask_em
- 分钟序列：stock_board_industry_hist_em(period=1/5/...) / stock_zh_a_hist_min_em / index_zh_a_hist_min_em
- 日线历史：stock_board_industry_hist_em(period=daily) / stock_zh_a_hist(qfq) / stock_zh_index_daily_em
- 资金流：  stock_individual_fund_flow_rank / stock_market_fund_flow
- 静态信息： stock_individual_info_em / tool_trade_date_hist_sina
"""
import time
from functools import wraps
from datetime import datetime

import numpy as np
import pandas as pd
import akshare as ak

from utils import get_logger, today_str, _now

logger = get_logger("data")

# akshare 中文列名 -> 标准英文列名（含东财/同花顺/新浪多源差异）
_COLUMN_MAP = {
    "日期": "date", "时间": "date",
    "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
    "开盘价": "open", "收盘价": "close", "最高价": "high", "最低价": "low",
    "成交量": "volume", "成交额": "amount",
    "涨跌幅": "pct_chg", "涨跌额": "chg", "振幅": "amplitude", "换手率": "turnover",
    "量比": "volume_ratio", "最新价": "price",
}

_cache = {}

# 主数据源健康状态：失败一次后本进程内直接使用备用源，避免反复超时
_source_status = {}


def _cache_get(key):
    item = _cache.get(key)
    if item is not None and item[0] > time.time():
        return item[1]
    if item is not None:
        _cache.pop(key, None)
    return None


def _cache_set(key, value, ttl):
    if ttl is not None and ttl > 0:
        _cache[key] = (time.time() + ttl, value)


def ttl_cached(ttl_provider):
    """TTL 缓存装饰器：ttl_provider(self) -> 秒数；None 表示不缓存。"""
    def deco(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            ttl = ttl_provider(self)
            if ttl is None:
                return fn(self, *args, **kwargs)
            key = (fn.__name__, args, tuple(sorted(kwargs.items())))
            hit = _cache_get(key)
            if hit is not None:
                return hit
            value = fn(self, *args, **kwargs)
            _cache_set(key, value, ttl)
            return value
        return wrapper
    return deco


class DataFetcher:
    """数据获取统一入口。"""

    def __init__(self, config):
        self.cfg = config.get("data", {})
        self.retry_times = self.cfg.get("retry_times", 3)
        self.retry_backoff = self.cfg.get("retry_backoff", 1.5)
        self.timeout = self.cfg.get("timeout", 15)
        self.indices = self.cfg.get("indices", [
            {"name": "上证指数", "symbol": "sh000001"},
            {"name": "创业板指", "symbol": "sz399006"},
            {"name": "科创50", "symbol": "sh000688"},
        ])
        self._trade_dates = None

    # ---------- 通用 ----------
    def _retry(self, fn, retries=None, *args, **kwargs):
        times = retries if retries is not None else self.retry_times
        last = None
        for i in range(times):
            try:
                return fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 网络/接口异常统一重试
                last = e
                logger.warning("接口 %s 第 %d 次失败: %s", getattr(fn, "__name__", "?"), i + 1, e)
                time.sleep(self.retry_backoff ** i)
        raise last

    def _pick_source(self, primary, backup, primary_name, backup_name, retries=1, *args, **kwargs):
        """主源优先，失败一次即标记不可用（进程内黑名单），后续直连备用源。"""
        status = _source_status.get(primary_name, {})
        if not status.get("down"):
            try:
                return self._retry(primary, retries, *args, **kwargs)
            except Exception as e:  # noqa: BLE001
                _source_status[primary_name] = {"down": True, "down_at": time.time()}
                logger.warning("主源 %s 不可用，本次及后续直连备用源 %s: %s",
                               primary_name, backup_name, e)
        return self._retry(backup, self.retry_times, *args, **kwargs)

    @staticmethod
    def _normalize(df):
        """中文列名转英文标准列名；日期列统一规范为 datetime（兼容 20260807 / 2026-08-07 / 时间戳）并升序。"""
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns=_COLUMN_MAP)
        if "date" in df.columns:
            s = df["date"].astype(str).str.strip()
            s = s.str.replace(r"^(\d{4})(\d{2})(\d{2})$", r"\1-\2-\3", regex=True)
            df["date"] = pd.to_datetime(s, errors="coerce")
            df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        return df

    # ---------- 交易日历 ----------
    def get_trade_dates(self):
        if self._trade_dates is None:
            df = self._retry(ak.tool_trade_date_hist_sina)
            self._trade_dates = set(pd.to_datetime(df["trade_date"]).dt.date)
        return self._trade_dates

    def is_trading_day(self, d=None):
        d = d or _now().date()
        try:
            return d in self.get_trade_dates()
        except Exception:  # noqa: BLE001 日历接口失败时按工作日兜底
            return d.weekday() < 5

    # ---------- 实时快照 ----------
    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 120))
    def get_industry_snapshot(self):
        """全行业板块实时行情。东财优先，失败降级同花顺（§3.1 多源容错）。"""
        def _em():
            return ak.stock_board_industry_name_em()

        def _ths():
            df = ak.stock_board_industry_summary_ths()
            if df is None or df.empty:
                raise ValueError("同花顺行业快照为空")
            return pd.DataFrame({
                "板块名称": df["板块"].astype(str),
                "最新价": df.get("均价", pd.Series(index=df.index)),
                "涨跌幅": df["涨跌幅"],
                "换手率": np.nan,
            })

        return self._pick_source(_em, _ths, "stock_board_industry_name_em",
                                 "stock_board_industry_summary_ths")

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 120))
    def get_stock_spot(self):
        """全 A 股实时快照。东财源，主源失败一次即黑名单快速失败（调用方降级腾讯接口）。"""
        status = _source_status.get("stock_zh_a_spot_em", {})
        if status.get("down"):
            raise ConnectionError("东财全市场快照不可达（已黑名单），请使用降级路径")
        try:
            return self._retry(ak.stock_zh_a_spot_em, 1)
        except Exception as e:  # noqa: BLE001
            _source_status["stock_zh_a_spot_em"] = {"down": True, "down_at": time.time()}
            logger.warning("主源 stock_zh_a_spot_em 不可用，本次及后续快速失败走降级: %s", e)
            raise

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 120))
    def get_index_snapshot(self):
        """三大指数实时快照（按 config 过滤）。东财优先，失败降级新浪。"""
        names = [i["name"] for i in self.indices]

        def _em():
            df = ak.stock_zh_index_spot_em()
            df = df[df["名称"].isin(names)].copy()
            return self._normalize(df)

        def _sina():
            df = ak.stock_zh_index_spot_sina()
            df = df[df["名称"].isin(names)].copy()
            df = df.rename(columns={"最新价": "price", "涨跌幅": "pct_chg"})
            return df.reset_index(drop=True)

        return self._pick_source(_em, _sina, "stock_zh_index_spot_em",
                                 "stock_zh_index_spot_sina")

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 30))
    def get_bid_ask(self, symbol):
        """个股五档盘口。"""
        return self._retry(ak.stock_bid_ask_em, symbol=symbol)

    # ---------- 历史行情 ----------
    @staticmethod
    def _start_date_3y():
        """默认历史窗口：3 年前（约 750 交易日），控制拉取体积与耗时。"""
        from datetime import timedelta
        return (_now() - timedelta(days=365 * 3)).strftime("%Y%m%d")

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_close", 86400))
    def get_stock_history(self, symbol, period="daily", adjust="qfq"):
        """个股历史日线（默认前复权，近 3 年）。东财优先，失败降级新浪。"""
        start = self._start_date_3y()

        def _em():
            return ak.stock_zh_a_hist(symbol=symbol, period=period,
                                      start_date=start, end_date=today_str(), adjust=adjust)

        def _sina():
            prefix = "sh" if str(symbol).startswith("6") else "sz"
            df = ak.stock_zh_a_daily(symbol=prefix + str(symbol), adjust="qfq")
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df[df["date"] >= pd.Timestamp(start)]
            return df

        df = self._pick_source(_em, _sina, "stock_zh_a_hist", "stock_zh_a_daily")
        return self._normalize(df)

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_close", 86400))
    def get_industry_history(self, name, period="daily"):
        """行业指数历史日线（近 3 年）。东财优先，失败降级同花顺。"""
        start = self._start_date_3y()

        def _em():
            return ak.stock_board_industry_hist_em(symbol=name, period=period,
                                                   start_date=start,
                                                   end_date=today_str(), adjust="")

        def _ths():
            df = ak.stock_board_industry_index_ths(symbol=name,
                                                   start_date=start,
                                                   end_date=today_str())
            return df

        df = self._pick_source(_em, _ths, "stock_board_industry_hist_em",
                               "stock_board_industry_index_ths")
        return self._normalize(df)

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_close", 86400))
    def get_index_history(self, symbol):
        """指数历史日线（三大指数）。东财优先，失败降级新浪。"""
        def _em():
            return ak.stock_zh_index_daily_em(symbol=symbol)

        def _sina():
            return ak.stock_zh_index_daily(symbol=symbol)

        df = self._pick_source(_em, _sina, "stock_zh_index_daily_em",
                               "stock_zh_index_daily")
        return self._normalize(df)

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_minute", 300))
    def get_stock_minute(self, symbol, period="5"):
        """个股分钟线（盘中实时因子）。"""
        df = self._retry(ak.stock_zh_a_hist_min_em, symbol=symbol, period=period,
                         start_date=today_str() + " 09:30:00", end_date=today_str() + " 15:00:00")
        return self._normalize(df)

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_minute", 300))
    def get_index_minute(self, symbol, period="5"):
        """指数分钟线（三大指数盘中实时概率）。"""
        df = self._retry(ak.index_zh_a_hist_min_em, symbol=symbol, period=period,
                         start_date=today_str() + " 09:30:00", end_date=today_str() + " 15:00:00")
        return self._normalize(df)

    # ---------- 资金流 ----------
    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 120))
    def get_fund_flow_rank(self, indicator="今日"):
        """全市场个股资金流实时排行（东财源，主源失败黑名单快速失败）。"""
        status = _source_status.get("stock_individual_fund_flow_rank", {})
        if status.get("down"):
            raise ConnectionError("东财资金流接口不可达（已黑名单）")
        try:
            return self._retry(ak.stock_individual_fund_flow_rank, 1, indicator=indicator)
        except Exception as e:  # noqa: BLE001
            _source_status["stock_individual_fund_flow_rank"] = {"down": True, "down_at": time.time()}
            logger.warning("主源 stock_individual_fund_flow_rank 不可用，本次及后续快速失败: %s", e)
            raise

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 120))
    def get_market_fund_flow(self):
        """大盘资金流。"""
        return self._retry(ak.stock_market_fund_flow)

    # ---------- 静态信息与解析 ----------
    @ttl_cached(lambda self: 86400 * 7)
    def get_stock_info(self, symbol):
        """个股基本信息（名称/行业等），返回 dict。"""
        df = self._retry(ak.stock_individual_info_em, symbol=symbol)
        return dict(zip(df["item"], df["value"]))

    def _tencent_stock_name(self, symbol):
        """腾讯行情单股接口获取股票名称（东财全市场快照不可达时的备用）。"""
        return self.get_stock_quote(symbol)["name"]

    def _tencent_search(self, name):
        """腾讯 smartbox 搜索：股票名称 -> (code, name)。"""
        import codecs
        import requests
        from urllib.parse import quote
        url = f"https://smartbox.gtimg.cn/s3/?q={quote(str(name))}&t=all&c=1"
        resp = requests.get(url, timeout=self.timeout)
        resp.encoding = "gbk"
        text = resp.text
        if 'v_hint="' not in text:
            raise ValueError(f"未找到股票: {name}")
        payload = text.split('v_hint="', 1)[1].rsplit('"', 1)[0]
        for item in payload.split("^"):
            parts = item.split("~")
            if len(parts) >= 3 and parts[0] in ("sh", "sz"):
                real_name = codecs.decode(parts[2], "unicode_escape")
                return parts[1], real_name
        raise ValueError(f"未找到股票: {name}")

    @ttl_cached(lambda self: self.cfg.get("cache_seconds_intraday", 120))
    def get_stock_quote(self, symbol):
        """腾讯单股实时行情（最新价/涨跌幅/换手率/量比），东财快照不可达时的备用。"""
        import requests
        prefix = "sh" if str(symbol).startswith("6") else "sz"
        resp = requests.get(f"https://qt.gtimg.cn/q={prefix}{symbol}", timeout=self.timeout)
        resp.encoding = "gbk"
        parts = resp.text.split("~")
        if len(parts) < 50 or not parts[1]:
            raise ValueError(f"未找到股票: {symbol}")

        def _g(i, d=0.0):
            try:
                return float(parts[i])
            except (TypeError, ValueError, IndexError):
                return d

        return {
            "name": parts[1],
            "price": _g(3),
            "pct_chg": _g(32),
            "turnover": _g(38),
            "volume_ratio": _g(49),
        }

    def resolve_stock(self, text):
        """解析用户输入 -> (symbol, name)。支持 6 位代码或股票名称（东财快照不可达时降级腾讯接口）。"""
        text = str(text).strip()
        if text.isdigit() and len(text) == 6:
            try:
                spot = self.get_stock_spot()
                row = spot[spot["代码"] == text]
                if not row.empty:
                    return text, str(row.iloc[0]["名称"])
            except Exception:  # noqa: BLE001 东财快照不可达时用腾讯接口
                pass
            return text, self._tencent_stock_name(text)
        # 名称解析：优先东财全市场快照（精确/模糊），失败降级腾讯 smartbox
        spot = None
        try:
            spot = self.get_stock_spot()
        except Exception:  # noqa: BLE001
            pass
        if spot is not None and not spot.empty:
            row = spot[spot["名称"] == text]
            if not row.empty:
                return str(row.iloc[0]["代码"]), str(text)
            row = spot[spot["名称"].str.contains(text, na=False)]
            if not row.empty:
                hit = row.iloc[0]
                return str(hit["代码"]), str(hit["名称"])
        try:
            return self._tencent_search(text)
        except Exception:  # noqa: BLE001
            pass
        raise ValueError(f"未找到股票: {text}")

    def get_stock_industry(self, symbol):
        """个股所属行业（供行业传导与行业分析）。"""
        try:
            info = self.get_stock_info(symbol)
            industry = info.get("行业", None)
            if industry and pd.notna(industry):
                return str(industry)
        except Exception as e:  # noqa: BLE001
            logger.warning("获取 %s 行业信息失败: %s", symbol, e)
        return None
