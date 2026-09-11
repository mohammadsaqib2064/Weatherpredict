"""In-process TTL cache with a generation token for bulk invalidation."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_LOCK = threading.Lock()
_STORE: dict[str, tuple[float, Any]] = {}
_GENERATION = 1


def get(key: str) -> Any | None:
    with _LOCK:
        entry = _STORE.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at and expires_at < time.time():
            _STORE.pop(key, None)
            return None
        return value


def set(key: str, value: Any, ttl: int | None = 60) -> None:  # noqa: A001
    with _LOCK:
        _STORE[key] = (time.time() + ttl if ttl else 0.0, value)


def get_or_set(key: str, factory: Callable[[], Any], ttl: int | None = 60, refresh: bool = False) -> Any:
    if not refresh:
        cached = get(key)
        if cached is not None:
            return cached
    value = factory()
    set(key, value, ttl)
    return value


def generation() -> int:
    return _GENERATION


def invalidate() -> None:
    """Bump the generation token; all generation-scoped keys become unreachable."""
    global _GENERATION
    with _LOCK:
        _GENERATION += 1
        _STORE.clear()


def clear() -> None:
    with _LOCK:
        _STORE.clear()
