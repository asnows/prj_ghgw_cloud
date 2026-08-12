"""数据层：SQLite（默认，零依赖本地可跑）+ PostgreSQL（生产，Supabase 等）。

通过 DATABASE_URL 自动选择：
- sqlite:///./xxx.db   → SQLite（默认）
- postgres:// 或 postgresql:// → PostgreSQL（需 psycopg2-binary）

表：
- users        客户（按设备指纹/激活码关联）
- licenses     激活码（核心：code / 等级 / 到期日 / 设备绑定）
- orders       支付订单（微信支付回调写入）
- usage_logs   用量统计（verify/analyze 时记录）
"""
import os
from contextlib import contextmanager
from datetime import datetime

from .config import get_settings

_DB_PATH = None
_DB_DRIVER = None  # "sqlite" | "postgres"


def _db_driver():
    global _DB_DRIVER
    if _DB_DRIVER is None:
        url = get_settings().DATABASE_URL
        _DB_DRIVER = "postgres" if url.startswith(("postgres://", "postgresql://")) else "sqlite"
    return _DB_DRIVER


def _db_path():
    global _DB_PATH
    if _DB_PATH is None:
        url = get_settings().DATABASE_URL
        # sqlite:///./xxx.db -> ./xxx.db；容器内默认 /tmp（保证可写）
        _DB_PATH = url.replace("sqlite:///", "", 1) if url.startswith("sqlite") else "/tmp/ghgw_cloud.db"
    return _DB_PATH


def _conn():
    if _db_driver() == "postgres":
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(get_settings().DATABASE_URL)
        conn.row_factory = None
        return conn, RealDictCursor
    import sqlite3
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn, None


class _SqliteCompat:
    """SQLite 连接兼容包装：调用方统一用 %s 占位符（PostgreSQL 风格），
    此处自动转换为 sqlite3 的 ? 占位符。"""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, args=None):
        q = sql.replace("%s", "?")
        if args is None:
            return self._conn.execute(q)
        return self._conn.execute(q, args)

    def executescript(self, sql):
        return self._conn.executescript(sql)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def db():
    if _db_driver() == "postgres":
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(get_settings().DATABASE_URL, cursor_factory=RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return
    import sqlite3
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield _SqliteCompat(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


_DDL_SQLITE = """
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

_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    device_fingerprint TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    order_id TEXT UNIQUE NOT NULL,
    platform TEXT NOT NULL,
    amount INTEGER NOT NULL,
    plan TEXT,
    license_code TEXT,
    status TEXT NOT NULL DEFAULT 'paid',
    paid_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_logs (
    id SERIAL PRIMARY KEY,
    license_code TEXT,
    tool TEXT,
    device_fingerprint TEXT,
    ts TEXT NOT NULL
);
"""


def init_db():
    """建表（幂等，按方言执行）。"""
    ddl = _DDL_POSTGRES if _db_driver() == "postgres" else _DDL_SQLITE
    with db() as conn:
        if _db_driver() == "postgres":
            # psycopg2 一次只能执行一条语句，按分号拆分
            for stmt in ddl.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.cursor().execute(stmt)
            conn.commit()
        else:
            conn.executescript(ddl)
