"""Per-request SQLite transaction guard for the dashboard API.

Database connections are cached per thread (``database.get_connection``) and
reused by later requests on the same threadpool thread. If a handler runs DML
and then raises (e.g. a 400 after a DELETE), the open transaction would keep
the database write lock until something on that thread commits. Every route
built with ``TxGuardRoute`` rolls back anything left open when its handler
returns, in the same thread that ran it (sync handlers run in the threadpool,
so a middleware or yield-dependency teardown could land on a different thread).
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from fastapi.routing import APIRoute

from jobwright.database import rollback_open_transactions


def guard_endpoint(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a plain sync endpoint so it rolls back leftover transactions on exit.

    Async endpoints and generators are returned unchanged: they don't run in a
    dedicated thread, so there is no thread whose connections are ours alone.
    """
    if (
        getattr(fn, "_tx_guarded", False)
        or not inspect.isfunction(fn)
        or inspect.iscoroutinefunction(fn)
        or inspect.isgeneratorfunction(fn)
        or inspect.isasyncgenfunction(fn)
    ):
        return fn

    @functools.wraps(fn)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        finally:
            rollback_open_transactions()

    guarded._tx_guarded = True  # type: ignore[attr-defined]
    return guarded


class TxGuardRoute(APIRoute):
    """APIRoute whose sync endpoint never leaves a transaction open."""

    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, guard_endpoint(endpoint), **kwargs)
