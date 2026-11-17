"""Starlette 1.6+ TestClient should use httpx2 so the suite stays warning-free."""

from __future__ import annotations


def test_starlette_testclient_binds_httpx2():
    import httpx2
    import starlette.testclient as tc

    assert tc.httpx is httpx2
