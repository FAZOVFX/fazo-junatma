"""In-process locks for wallet, payment, and registration critical sections."""

import asyncio

_LOCKS: dict[str, asyncio.Lock] = {}


def resource_lock(scope: str, identifier: int | str) -> asyncio.Lock:
    key = f"{scope}:{identifier}"
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock
