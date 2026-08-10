"""数据层：SQLite 起步（零依赖本地可跑），预留 PostgreSQL 切换。

表：
- users        客户（按设备指纹/激活码关联）
- licenses     激活码（核心：code / 等级 / 到期日 / 设备绑定）
- orders       支付订单（微信支付回调写入）
- usage_logs   用量统计（verify/analyze 时记录）
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import get_settings

_DB_PATH = None


def _db_path():
    global _DB_PATH
    if _DB_PATH is None:
        url = get_settings().DATABASE_URL
        # sqlite:///./xxx.db -> ./xxx.db
        _DB_PATH = url.replace("sqlite:///", "", 1) if url.startswith("sqlite") else "./ghgw_cloud.db"
    return _DB_PATH


def _conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db():
    conn = _conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def init_db():
    """建表（幂等）。"""
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_fingerprint TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                plan TEXT NOT NULL,
                days INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                devices TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                platform TEXT NOT NULL,
                amount INTEGER NOT NULL,
                plan TEXT,
                license_code TEXT,
                status TEXT NOT NULL DEFAULT 'paid',
                paid_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_code TEXT,
                tool TEXT,
                device_fingerprint TEXT,
                ts TEXT NOT NULL
            );
            """
        )
