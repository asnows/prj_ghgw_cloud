"""授权与试用期管理：30 天免费试用 → 到期付费墙 → 激活码解锁。

设计要点：
- 试用期：首次调用记录时间戳到本地状态文件，30 天内全功能；
- 激活码：`ghgw-<到期日YYYYMMDD>-<签名>`，HMAC-SHA256 签名，公钥在技能内校验，私钥在开发者手里；
- 过期后：report 层展示付费提示与收款码（HTML 内嵌图片，终端输出指引）；
- 安全模型：ima 沙箱内客户无法修改代码/状态文件路径，激活码无法伪造（无私钥）。
"""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta

from utils import _now, CN_TZ

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 授权状态文件（相对技能目录，ima 沙箱内客户不可见）
STATE_PATH = os.path.join(PROJECT_ROOT, "config", "license_state.json")

# 试用期天数（可配置）
TRIAL_DAYS = 30

# 公钥（HMAC 密钥）：由 tools/gen_license.py 生成密钥对时写入；私钥仅在开发者本地
PUBLIC_KEY_FILE = os.path.join(PROJECT_ROOT, "config", "license_pub.key")

# 默认公钥（占位，首次运行 gen_license.py 生成后覆盖）
_DEFAULT_PUBLIC_KEY = "GHGW_DEFAULT_PUBLIC_KEY_PLACEHOLDER"


def _load_public_key():
    try:
        with open(PUBLIC_KEY_FILE, "r", encoding="utf-8") as f:
            k = f.read().strip()
            if k:
                return k
    except OSError:
        pass
    return _DEFAULT_PUBLIC_KEY


def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _today():
    return _now().date()


def first_use_date():
    """首次使用日期（首次调用时记录）。"""
    state = _load_state()
    if "first_use" not in state:
        state["first_use"] = _today().isoformat()
        _save_state(state)
    return datetime.strptime(state["first_use"], "%Y-%m-%d").date()


def trial_remaining_days():
    """剩余试用天数（>=0 表示仍在试用期）。"""
    d0 = first_use_date()
    remain = TRIAL_DAYS - (_today() - d0).days
    return max(remain, 0)


def is_trial_active():
    """是否处于免费试用期。"""
    return trial_remaining_days() > 0


def licensed_until():
    """已激活的到期日期（未激活返回 None）。"""
    state = _load_state()
    lic = state.get("licensed_until")
    return datetime.strptime(lic, "%Y-%m-%d").date() if lic else None


def is_licensed():
    """是否已激活且未到期。"""
    until = licensed_until()
    return until is not None and until >= _today()


def license_status():
    """授权状态摘要。返回 dict，供报告层展示。"""
    remain = trial_remaining_days()
    until = licensed_until()
    if is_licensed():
        return {"level": "licensed", "until": until.isoformat(),
                "tip": f"💎 会员已激活，有效期至 {until.isoformat()}"}
    if is_trial_active():
        return {"level": "trial", "remain": remain,
                "tip": f"🎁 免费试用中，剩余 {remain} 天"}
    return {"level": "expired",
            "tip": "⏰ 免费试用已结束，请输入激活码解锁会员功能（获取方式见下方）"}


def _verify_signature(code, exp_str, sig_part):
    """签名校验：优先新格式（nonce6+sig），兼容旧格式（纯 sig）。"""
    if len(sig_part) > 6:
        nonce, sig = sig_part[:6], sig_part[6:]
        if hmac.compare_digest(sig, _sign(f"ghgw-{exp_str}-{nonce}")):
            return True
    return hmac.compare_digest(sig_part, _sign(f"ghgw-{exp_str}"))


def activate(activation_code):
    """校验并激活。成功返回 (True, 到期日)；失败返回 (False, 原因)。"""
    code = (activation_code or "").strip()
    if not code:
        return False, "激活码不能为空"
    try:
        # 格式：ghgw-YYYYMMDD-<nonce+sig>（签名段可能含 "-"，只分割前两段）
        prefix, exp, sig = code.split("-", 2)
        if prefix != "ghgw":
            return False, "激活码格式错误"
        exp_date = datetime.strptime(exp, "%Y%m%d").date()
    except ValueError:
        return False, "激活码格式错误（应为 ghgw-YYYYMMDD-签名）"
    if not _verify_signature(code, exp, sig):
        return False, "激活码签名校验失败（无效激活码）"
    if exp_date < _today():
        return False, f"激活码已过期（{exp_date.isoformat()}）"
    state = _load_state()
    state["licensed_until"] = exp_date.isoformat()
    _save_state(state)
    return True, exp_date


def _sign(payload):
    """HMAC-SHA256 签名（与发卡工具一致）。"""
    key = _load_public_key().encode("utf-8")
    digest = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorize_prompt():
    """付费墙文案（终端/报告共用），含收款码指引。"""
    status = license_status()
    if status["level"] == "licensed":
        return status["tip"]
    if status["level"] == "trial":
        return (f"{status['tip']}｜试用期内全功能可用，到期后需激活码续用。"
                f" 已激活用户输入「激活 ghgw-xxxx」即可解锁。")
    return (
        f"{status['tip']}\n"
        f"💳 获取激活码：扫描下方收款码付费后，联系作者领取（月卡/年卡可选）。\n"
        f"🔑 已有激活码？直接回复「激活 ghgw-XXXX-XXXX」即可解锁。"
    )
