"""模型版本存储：model/ 目录管理（权重表、校准器、生效版本指针）。

结构：
    model/weights_v{n}.json    各版本权重表
    model/calibrator_v{n}.pkl  各版本校准模型
    model/meta.json            当前生效版本指针（可回滚）
"""
import json
import os
import pickle

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model")
META_FILE = "meta.json"


def _path(name):
    return os.path.join(MODEL_DIR, name)


def list_versions():
    if not os.path.isdir(MODEL_DIR):
        return []
    versions = []
    for f in os.listdir(MODEL_DIR):
        if f.startswith("weights_v") and f.endswith(".json"):
            v = f.replace("weights_v", "").replace(".json", "")
            if v.isdigit():
                versions.append(int(v))
    return sorted(versions)


def next_version():
    vs = list_versions()
    return (vs[-1] + 1) if vs else 1


def save_version(weights, calibrator, meta):
    """保存新版本并设为生效。weights: dict；calibrator: 对象或 None；meta: dict。"""
    os.makedirs(MODEL_DIR, exist_ok=True)
    v = meta.get("version") or next_version()
    w_file = f"weights_v{v}.json"
    c_file = f"calibrator_v{v}.pkl"
    with open(_path(w_file), "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)
    if calibrator is not None:
        with open(_path(c_file), "wb") as f:
            pickle.dump(calibrator, f)
    meta["version"] = v
    meta["weights_file"] = w_file
    meta["calibrator_file"] = c_file if calibrator is not None else None
    with open(_path(META_FILE), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return v


def load_active_meta():
    if not os.path.exists(_path(META_FILE)):
        return None
    with open(_path(META_FILE), "r", encoding="utf-8") as f:
        return json.load(f)


def load_active_weights():
    """返回 {weights: {name: w}, bias, k}；无生效版本返回 {}。"""
    meta = load_active_meta()
    if not meta or not meta.get("weights_file"):
        return {}
    try:
        with open(_path(meta["weights_file"]), "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "weights": data.get("weights", {}),
            "bias": float(data.get("bias", 0.0)),
            "k": float(data.get("k", 1.0)),
            "version": meta.get("version"),
        }
    except Exception:  # noqa: BLE001 文件损坏视为无生效模型
        return {}


def load_active_calibrator():
    """返回校准器对象；无则 None。"""
    meta = load_active_meta()
    if not meta or not meta.get("calibrator_file"):
        return None
    path = _path(meta["calibrator_file"])
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:  # noqa: BLE001
        return None


def rollback():
    """回滚到上一版本（有生效版本时）。返回新生效版本号或 None。"""
    vs = list_versions()
    meta = load_active_meta()
    if not meta or not vs:
        return None
    cur = meta.get("version")
    older = [v for v in vs if v < cur] if cur else []
    if not older:
        return None
    target = older[-1]
    with open(_path(META_FILE), "w", encoding="utf-8") as f:
        json.dump({"active_version": target,
                   "weights_file": f"weights_v{target}.json",
                   "calibrator_file": f"calibrator_v{target}.pkl",
                   "updated_at": None,
                   "rolled_back_from": cur}, f, ensure_ascii=False, indent=2)
    return target
