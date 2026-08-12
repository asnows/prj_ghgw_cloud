"""开发者发卡工具：生成密钥对、生成激活码、批量发卡。

用法：
    python gen_license.py --gen-keys                    # 首次：生成密钥对（私钥仅存本地）
    python gen_license.py --code 30                     # 生成一个 30 天激活码
    python gen_license.py --code 365 --count 10         # 批量生成 10 个一年期激活码
    python gen_license.py --export month_codes.txt      # 导出到文本文件（可上传面包多自动发货）

激活码格式：ghgw-YYYYMMDD-<签名>（到期日 + HMAC 签名）
"""
import argparse
import base64
import hashlib
import hmac
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
PRIVATE_KEY_FILE = os.path.join(CONFIG_DIR, "license_private.key")  # 仅开发者本地，切勿分发
PUBLIC_KEY_FILE = os.path.join(CONFIG_DIR, "license_pub.key")       # 随技能分发


def gen_keys():
    """生成 HMAC 密钥对（实际是同密钥两份：私钥本地、公钥进技能）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    with open(PRIVATE_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(secret)
    with open(PUBLIC_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(secret)
    os.chmod(PRIVATE_KEY_FILE, 0o600)
    print(f"✅ 密钥已生成：\n  私钥（仅本地，勿分发）: {PRIVATE_KEY_FILE}\n  公钥（随技能分发）: {PUBLIC_KEY_FILE}")


def _sign(payload):
    with open(PRIVATE_KEY_FILE, "r", encoding="utf-8") as f:
        key = f.read().strip().encode("utf-8")
    digest = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_code(days, now=None):
    """生成激活码：ghgw-YYYYMMDD-签名。now 可注入日期（测试用）。"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    base = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    exp = (base + timedelta(days=days)).strftime("%Y%m%d")
    payload = f"ghgw-{exp}"
    return f"{payload}-{_sign(payload)}"


def main():
    parser = argparse.ArgumentParser(description="股海怪物 发卡工具")
    parser.add_argument("--gen-keys", action="store_true", help="生成密钥对")
    parser.add_argument("--code", type=int, default=0, help="生成激活码（天数，如 30/365）")
    parser.add_argument("--count", type=int, default=1, help="批量数量")
    parser.add_argument("--export", default=None, help="导出到文件（每行一个）")
    parser.add_argument("--test-date", default=None, help="测试用：基准日期 YYYY-MM-DD")
    args = parser.parse_args()

    if args.gen_keys:
        gen_keys()
        return
    if not os.path.exists(PRIVATE_KEY_FILE):
        print("❌ 未找到私钥，请先运行 --gen-keys")
        return

    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.strptime(args.test_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Shanghai")) if args.test_date else None

    codes = [make_code(args.code, now) for _ in range(args.count)]
    for c in codes:
        print(c)
    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            f.write("\n".join(codes) + "\n")
        print(f"✅ 已导出 {args.count} 个激活码到 {args.export}")


if __name__ == "__main__":
    main()
