"""公共工具：配置加载、日志、时间与模式判断、格式化。"""
import os
import sys
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

# A股市场时间基准：北京时间（UTC+8），报告时间、盘中判断、交易日日期均以此为准
CN_TZ = ZoneInfo("Asia/Shanghai")


def _now():
    """返回当前北京时间（带时区）。"""
    return datetime.now(CN_TZ)


def load_config(path=None):
    path = path or CONFIG_PATH
    with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig 兼容带/不带 BOM
        return yaml.safe_load(f) or {}


def get_logger(name="ghgw", level=logging.INFO):
    logger = logging.getLogger(name)
    if not logger.handlers:
        # MCP stdio 模式下 stdout 仅用于协议，日志走 stderr（GHGW_LOG_STDERR=1）
        stream = sys.stderr if os.environ.get("GHGW_LOG_STDERR") else sys.stdout
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def clamp(v, lo=-1.0, hi=1.0):
    """限幅到 [lo, hi]"""
    return max(lo, min(hi, v))


def pct(v, digits=1):
    """0.1234 -> '12.3%'"""
    return f"{v * 100:.{digits}f}%"


def today_str():
    return _now().strftime("%Y-%m-%d")


def now_str():
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def is_intraday_time(dt=None):
    """是否处于盘中时段（周一至周五 09:30-11:30 / 13:00-15:00，北京时间）。"""
    dt = dt or _now()
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return (time(9, 30) <= t <= time(11, 30)) or (time(13, 0) <= t <= time(15, 0))


def mode_of(dt=None, is_trading_day=True):
    """返回模式：'intraday' 盘中实时 / 'close' 收盘。"""
    dt = dt or _now()
    if is_trading_day and is_intraday_time(dt):
        return "intraday"
    return "close"


def data_basis(dt=None, is_trading_day=True):
    """四段式数据基准（北京时间，固化规则）：
    - intraday   交易日 09:30-11:30 / 13:00-15:00 → 盘中实时
    - noon       交易日 11:30-13:00               → 当日午盘（上午收盘快照，真实数据）
    - close      交易日 >=15:00                   → 当日收盘
    - prev_close 交易日 <09:30 或非交易日          → 上一交易日收盘（快照不可信，须回退）
    """
    dt = dt or _now()
    if not is_trading_day:
        return "prev_close"
    t = dt.time()
    if time(9, 30) <= t <= time(11, 30):
        return "intraday"
    if time(11, 30) < t < time(13, 0):
        return "noon"
    if time(13, 0) <= t <= time(15, 0):
        return "intraday"
    if t >= time(15, 0):
        return "close"
    return "prev_close"


def basis_label(basis, prev_date=None):
    """数据基准标注文本。"""
    if basis == "intraday":
        return "盘中实时"
    if basis == "noon":
        return "当日午盘"
    if basis == "close":
        return "当日收盘"
    if prev_date:
        return f"上一交易日收盘（{prev_date}）"
    return "上一交易日收盘"


def suggestion_of(prob, buy_threshold=0.70, sell_threshold=0.30):
    """按概率给出建议等级（与方案 §4.7 一致）。"""
    if prob >= 0.70:
        return "🟢 强烈看涨", "买入概率高，可考虑积极关注"
    if prob >= 0.55:
        return "🟢 看涨", "买入概率偏高，可逢低关注"
    if prob >= 0.45:
        return "🟡 中性", "观望为主"
    if prob >= 0.30:
        return "🔴 看跌", "卖出概率偏高，注意风险"
    return "🔴 强烈看跌", "卖出概率高，建议回避"


def status_label(prob_up):
    """模板状态标签（自选股列表 UI 规范）：潜在买入机会 / 观望 / 潜在卖出机会。"""
    if prob_up >= 0.70:
        return "🟢 潜在买入机会"
    if prob_up <= 0.30:
        return "🔴 潜在卖出机会"
    return "⚪ 观望"


def chg_arrow(v):
    """涨跌着色符号（A股红涨绿跌）：正=红▲，负=绿▼，平=灰—。"""
    if v is None or v != v:  # None / NaN
        return ""
    if v > 0:
        return "🔴 ▲"
    if v < 0:
        return "🟢 ▼"
    return "⚪ ➖"
