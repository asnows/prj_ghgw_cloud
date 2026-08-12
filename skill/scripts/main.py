"""股海怪物 主入口：意图路由 + 参数解析 + 输出格式化。

用法：
    python main.py "分析行业"
    python main.py "600519"
    python main.py "回测600519"
    python main.py "调优模型"
    echo "贵州茅台怎么样" | python main.py
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import load_config, get_logger  # noqa: E402
from data_fetcher import DataFetcher  # noqa: E402

logger = get_logger("main")

HELP_TEXT = """🤖 股海怪物 · 使用说明

📊 市场与行业分析：分析行业 / 哪些行业值得买 / 看看半导体板块
📈 个股分析：600519 / 贵州茅台怎么样
🕐 回测：回测600519 / 回测贵州茅台 2024-01-01 2025-01-01
🧠 模型调优：调优模型 / 重新训练一下权重

⚠️ 本工具输出为统计概率参考，不构成投资建议。
"""

_INDUSTRY_KEYWORDS = ("行业", "板块", "大盘", "指数", "值得", "买入", "卖出", "行情", "市场")
_TUNE_KEYWORDS = ("调优", "训练", "重训", "调参")
_HELP_KEYWORDS = ("帮助", "用法", "怎么用", "help")
_CODE_RE = re.compile(r"\d{6}")


def _match_industry(text, fetcher):
    """尝试从输入中识别指定行业名（精确/包含匹配行业板块列表）。"""
    try:
        snap = fetcher.get_industry_snapshot()
        if snap is None or snap.empty:
            return None
        names = [str(x) for x in snap["板块名称"].tolist()]
    except Exception:  # noqa: BLE001
        return None
    for n in names:
        if n and n in text:
            return n
    return None


def _route(text, config, fetcher):
    t = text.strip()
    if not t:
        return HELP_TEXT

    # 激活码指令：激活 ghgw-XXXX
    if "激活" in t or "ghgw-" in t:
        from license import activate
        m = re.search(r"ghgw-[\w-]+", t)
        code = m.group(0) if m else ""
        ok, result = activate(code)
        if ok:
            return (f"✅ 激活成功！会员有效期至 {result.isoformat()}。\n"
                    f"🎉 感谢支持，现在开始使用股海怪物全部功能。\n\n"
                    f"⚠️ 本结果由量化模型生成，仅供参考，不构成投资建议。")
        return (f"❌ 激活失败：{result}\n"
                f"💳 获取激活码：扫描报告中的收款码付费后联系作者领取。\n"
                f"🔑 输入格式：激活 ghgw-YYYYMMDD-签名")

    if "回测" in t:
        from backtest import run_backtest
        return run_backtest(t, config, fetcher)

    if any(k in t for k in _TUNE_KEYWORDS):
        from tuning import run_tuning
        return run_tuning(config, fetcher)

    if any(k in t for k in _HELP_KEYWORDS):
        return HELP_TEXT

    # 行业相关（含指定行业）
    if any(k in t for k in _INDUSTRY_KEYWORDS):
        from industry_analysis import IndustryAnalyzer
        analyzer = IndustryAnalyzer(config, fetcher)
        target = _match_industry(t, fetcher)
        if target:
            return analyzer.run_single(target)
        return analyzer.run()

    # 个股：6 位代码
    if _CODE_RE.search(t):
        from stock_analysis import StockAnalyzer
        try:
            return StockAnalyzer(config, fetcher).analyze(t)
        except Exception as e:  # noqa: BLE001
            return f"❌ 个股分析失败：{e}"

    # 其他文本尝试按股票名称解析
    if not t.isascii() or " " in t:
        from stock_analysis import StockAnalyzer
        try:
            return StockAnalyzer(config, fetcher).analyze(t)
        except Exception as e:  # noqa: BLE001
            logger.info("按股票名称解析失败: %s", e)
            return f"❌ 股海怪物：未识别「{t}」：{e}\n提示：可用 6 位代码（如 600519），或输入「帮助」查看用法。"
    return HELP_TEXT


def _export_html(report_text, text, out_dir):
    """将文本报告导出为带品牌 Logo 的 HTML 报告（logo 内嵌 base64，单文件可分享）。"""
    try:
        from report_html import save_report_html
        title = f"股海怪物 · {text.strip()[:20]}"
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"gu_hai_guai_wu_report_{ts}.html")
        save_report_html(report_text, out_path, title=title)
        return out_path
    except Exception as e:  # noqa: BLE001
        logger.warning("HTML 报告导出失败: %s", e)
        return None


def main():
    parser = argparse.ArgumentParser(description="股海怪物")
    parser.add_argument("query", nargs="?", default=None, help="自然语言指令")
    parser.add_argument("--no-html", action="store_true", help="关闭 HTML 报告导出（默认每次分析自动导出带品牌 Logo 的 HTML 报告）")
    parser.add_argument("--out-dir", default=None, help="HTML 报告输出目录（默认 skill 目录下 outputs/）")
    args = parser.parse_args()

    text = args.query
    if text is None:
        text = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    if not text:
        print(HELP_TEXT)
        return

    config = load_config()
    fetcher = DataFetcher(config)
    try:
        result = _route(text, config, fetcher)
        print(result)
        if not args.no_html:
            out_dir = args.out_dir or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "outputs"
            )
            out_path = _export_html(result, text, out_dir)
            if out_path:
                print(f"\n📄 HTML 报告已导出（含品牌 Logo）：{out_path}")
            else:
                print("\n⚠️ HTML 报告导出失败，请检查 logo 文件与依赖。")
    except KeyboardInterrupt:
        print("\n已取消。")
    except Exception as e:  # noqa: BLE001
        logger.exception("执行失败")
        print(f"❌ 执行失败：{e}\n\n请稍后重试，或输入「帮助」查看用法。")


if __name__ == "__main__":
    main()
