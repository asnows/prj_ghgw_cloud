"""因子注册表：自动扫描 factors/ 下所有模块并收集 @register 装饰的因子类。"""
import importlib
import pkgutil

from .base import (  # noqa: F401 重新导出
    BaseFactor,
    FactorContext,
    FactorResult,
    _REGISTRY,
    get_factor_classes as _base_get_factor_classes,
    register,
)


def _discover():
    for mod in pkgutil.iter_modules(__path__):
        if mod.name == "base":
            continue
        importlib.import_module(f"{__name__}.{mod.name}")


def get_factor_classes():
    """返回 {name: class} 注册表（首次调用触发自动扫描）。"""
    if not _REGISTRY:
        _discover()
    return _base_get_factor_classes()


def list_factors():
    return sorted(get_factor_classes().keys())
