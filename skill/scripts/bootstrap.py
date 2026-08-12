"""依赖引导脚本：确保 akshare / pandas / numpy / scikit-learn 等依赖可用。

为什么需要它：沙箱环境的系统 site-packages 可能被重置，而 workspace 是持久区。
本脚本将依赖安装到持久目录（默认 workspace 下 .pylibs），装一次永久有效；
每次运行前自动检测，缺失才补装，避免反复手动 pip install。

用法：
    python bootstrap.py                # 仅检查 + 补装依赖
    python bootstrap.py --run "行业分析"  # 补装后直接运行 main.py
"""
import os
import sys
import subprocess

# (import 名, pip 安装名)：import 模块名与 PyPI 包名可能不一致（sklearn/scikit-learn、yaml/PyYAML）
REQUIRED = [
    ("akshare", "akshare"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("sklearn", "scikit-learn"),
    ("yaml", "PyYAML"),
    ("requests", "requests"),
    ("markdown", "markdown"),
]

# pip 镜像源：默认清华源（国内加速，首次安装从 10+ 分钟降至 2-5 分钟），可用 GHGW_PIP_INDEX 覆盖
PIP_INDEX = os.environ.get("GHGW_PIP_INDEX", "https://pypi.tuna.tsinghua.edu.cn/simple")

# 持久依赖目录：workspace 根下 .pylibs（沙箱中仅 workspace 持久，系统 site-packages 可能被重置）
# 候选路径（按优先级）：环境变量 > 沙箱固定路径 > 上级目录推算
def _persist_dir():
    cands = []
    env = os.environ.get("GHGW_PYLIBS")
    if env:
        cands.append(env)
    cands.append("/sandbox/workspace")
    cands.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))))
    for c in cands:
        p = os.path.join(c, ".pylibs")
        if os.path.isdir(p):
            return p
    return os.path.join(cands[0], ".pylibs")


PERSIST_DIR = _persist_dir()


def _importable(mod):
    try:
        __import__(mod)
        return True
    except Exception:  # noqa: BLE001 导入失败即视为缺失
        return False


def ensure_deps():
    """检测依赖，缺失则安装到持久目录；返回持久目录路径。"""
    sys.path.insert(0, PERSIST_DIR)
    missing = [pip_name for mod, pip_name in REQUIRED if not _importable(mod)]
    if missing:
        print(f"🔧 依赖缺失 {missing}，安装到持久目录 {PERSIST_DIR} ...")
        print(f"   镜像源: {PIP_INDEX}（首次安装约 2-5 分钟，仅需一次）")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--target", PERSIST_DIR, "-q",
             "-i", PIP_INDEX] + missing,
            stdout=sys.stderr,
        )
        sys.path.insert(0, PERSIST_DIR)
        still = [pip_name for mod, pip_name in REQUIRED if not _importable(mod)]
        if still:
            raise SystemExit(f"❌ 依赖安装失败，仍缺失: {still}")
        print("✅ 依赖就绪（已持久化，下次无需重装）")
    return PERSIST_DIR


if __name__ == "__main__":
    ensure_deps()
    if "--run" in sys.argv:
        idx = sys.argv.index("--run")
        query = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
        import main  # noqa: E402

        sys.argv = ["main.py"] + ([query] if query else [])
        main.main()
    else:
        print("✅ 依赖检查通过，可直接运行：python main.py \"行业分析\"")
