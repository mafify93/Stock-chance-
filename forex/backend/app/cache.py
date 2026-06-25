"""A tiny in-process TTL cache.

Forex data moves fast, so caches here are deliberately short-lived: they
exist only to smooth out bursts of identical requests (e.g. the screener
hitting the same pair from several code paths) and to stay polite to
OANDA's rate limits, not to serve stale prices.
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


cache = TTLCache()
