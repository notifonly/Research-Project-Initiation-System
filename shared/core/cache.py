from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from shared.core.config import settings
from shared.core.logging_setup import get_logger

CACHE_VERSION = "v1"

logger = get_logger("cache")


class ResponseCache:
    """SQLite-backed response cache with per-entry TTL.

    Two logical namespaces: "llm" and "mcp", stored in the same DB file.
    Thread-safe via asyncio lock.
    """

    _instance: Optional[ResponseCache] = None
    _lock = asyncio.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or settings.data_dir / "response_cache.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)"
            )
            conn.commit()
        self._purge_expired()

    def _purge_expired(self) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))
                conn.commit()
        except Exception:
            pass

    @classmethod
    async def get_instance(cls) -> ResponseCache:
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def _make_key(*parts: str) -> str:
        raw = "|".join((CACHE_VERSION,) + parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def get(self, namespace: str, *key_parts: str) -> Optional[str]:
        cache_key = self._make_key(namespace, *key_parts)
        try:
            async with self._write_lock:
                self._purge_expired()
                with sqlite3.connect(str(self._db_path)) as conn:
                    row = conn.execute(
                        "SELECT value, expires_at FROM cache WHERE key = ? AND namespace = ?",
                        (cache_key, namespace),
                    ).fetchone()
                    if row and row[1] > time.time():
                        return row[0]
            return None
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")
            return None

    async def set(self, namespace: str, value: str, ttl_seconds: int, *key_parts: str) -> None:
        cache_key = self._make_key(namespace, *key_parts)
        now = time.time()
        try:
            async with self._write_lock:
                with sqlite3.connect(str(self._db_path)) as conn:
                    conn.execute(
                        """INSERT OR REPLACE INTO cache (key, namespace, value, created_at, expires_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (cache_key, namespace, value, now, now + ttl_seconds),
                    )
                    conn.commit()
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    async def invalidate(self, namespace: Optional[str] = None) -> int:
        count = 0
        try:
            async with self._write_lock:
                with sqlite3.connect(str(self._db_path)) as conn:
                    if namespace:
                        cursor = conn.execute(
                            "DELETE FROM cache WHERE namespace = ?", (namespace,)
                        )
                    else:
                        cursor = conn.execute("DELETE FROM cache")
                    conn.commit()
                    count = cursor.rowcount
            logger.info(f"Cache invalidated: {count} entries (namespace={namespace or 'all'})")
        except Exception as e:
            logger.warning(f"Cache invalidate failed: {e}")
        return count


async def get_cache() -> ResponseCache:
    if not settings.llm_cache_enabled:
        raise RuntimeError("Cache is disabled")
    return await ResponseCache.get_instance()
