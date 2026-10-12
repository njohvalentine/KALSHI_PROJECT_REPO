import logging

import httpx2
import pytest

from app.kalshi import KalshiClient, KalshiError, KalshiNotFound
from tests.conftest import EMAIL, PASSWORD, needs_db

BASE = "https://kalshi.test/trade-api/v2"


def make(handler, **kw):
    sleeps: list[float] = []
    client = KalshiClient(
        BASE, client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        sleep=sleeps.append, **kw,
    )
    return client, sleeps


def test_list_markets_passes_params_and_returns_json_unchanged():
    seen = {}

    def handler(request):
        seen["url"] = request.url
        return httpx2.Response(200, json={"markets": [{"ticker": "A"}], "cursor": "next"})

    client, _ = make(handler)
    out = client.list_markets(status="open", limit=5, cursor="c1")
    assert out == {"markets": [{"ticker": "A"}], "cursor": "next"}
    assert seen["url"].path == "/trade-api/v2/markets"
    assert dict(seen["url"].params) == {"status": "open", "limit": "5", "cursor": "c1"}  # None params dropped


def test_paths_for_each_call():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx2.Response(200, json={})

    c, _ = make(handler)
    c.get_market("KX-1")
    c.get_candlesticks("SER", "KX-1", start_ts=1, end_ts=2, period_interval=60)
    c.get_historical_cutoff()
    c.list_historical_markets(limit=3)
    c.get_historical_candlesticks("KX-1", start_ts=1, end_ts=2, period_interval=1440)
    base = "/trade-api/v2"
    assert paths == [
        f"{base}/markets/KX-1",
        f"{base}/series/SER/markets/KX-1/candlesticks",
        f"{base}/historical/cutoff",
        f"{base}/historical/markets",
        f"{base}/historical/markets/KX-1/candlesticks",
    ]


def test_ticker_cannot_escape_its_path_segment():
    paths = []
    c, _ = make(lambda r: (paths.append(r.url.raw_path.decode()), httpx2.Response(200, json={}))[1])
    c.get_market("../../portfolio/balance")
    assert "/portfolio" not in paths[0].replace("%2F", "")  and "%2F" in paths[0]


def test_429_then_success_is_retried_and_logged(caplog):
    caplog.set_level(logging.WARNING, logger="app.kalshi")
    replies = iter([httpx2.Response(429), httpx2.Response(429, headers={"retry-after": "3"}), httpx2.Response(200, json={"ok": 1})])
    c, sleeps = make(lambda r: next(replies))
    assert c.get_historical_cutoff() == {"ok": 1}
    assert sleeps == [0.5, 3.0]  # exponential backoff, and Retry-After wins when larger
    assert caplog.text.count("Kalshi retry") == 2 and "rate limited" in caplog.text


def test_429_until_give_up_raises():
    calls = []
    c, sleeps = make(lambda r: (calls.append(1), httpx2.Response(429))[1], max_attempts=3)
    with pytest.raises(KalshiError, match="Giving up.*3 tries.*rate limited"):
        c.list_markets()
    assert len(calls) == 3 and len(sleeps) == 2


def test_connection_error_is_retried_then_raised(caplog):
    caplog.set_level(logging.WARNING, logger="app.kalshi")

    def handler(request):
        raise httpx2.ConnectError("boom")

    c, _ = make(handler, max_attempts=2)
    with pytest.raises(KalshiError, match="connection problem"):
        c.get_market("A")
    assert "Kalshi retry" in caplog.text


def test_404_and_other_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx2.Response(404 if request.url.path.endswith("/NOPE") else 500)

    c, sleeps = make(handler)
    with pytest.raises(KalshiNotFound):
        c.get_market("NOPE")
    with pytest.raises(KalshiError, match="HTTP 500"):
        c.get_market("OTHER")
    assert len(calls) == 2 and sleeps == []


@needs_db
def test_endpoints_need_login_and_map_errors(make_client):
    H = {"X-Requested-With": "t"}
    with make_client() as client:
        assert client.get("/api/markets").status_code == 401
        assert client.get("/api/markets/ABC").status_code == 401

        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)

        def handler(request):
            if request.url.path.endswith("/markets/MISSING"):
                return httpx2.Response(404)
            if request.url.path.endswith("/markets/BROKEN"):
                return httpx2.Response(500)
            return httpx2.Response(200, json={"markets": [{"ticker": "T1"}], "cursor": ""})

        client.app.state.kalshi = KalshiClient(BASE, client=httpx2.Client(transport=httpx2.MockTransport(handler)))
        assert client.get("/api/markets").json()["markets"][0]["ticker"] == "T1"
        assert client.get("/api/markets/MISSING").status_code == 404
        assert client.get("/api/markets/BROKEN").status_code == 502
        assert client.get("/api/markets?limit=0").status_code == 422


def test_default_client_fails_fast_when_kalshi_is_unreachable():
    c = KalshiClient(BASE)
    try:
        assert c._client.timeout.connect == 3.0 and c._client.timeout.read == 10.0
        assert c._max_attempts == 3
    finally:
        c.close()
