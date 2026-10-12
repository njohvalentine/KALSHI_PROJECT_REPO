"""The page fetcher's safety rules. No real network: names are resolved by a fake resolver and the
requests are answered by httpx2's mock transport, which also shows exactly what we would connect to."""

import gzip
import socket

import httpx2
import pytest
from alembic import command
from sqlalchemy.orm import Session as DbSession

from app.config import load_settings
from app.models import SourcePage
from app.research import fetch
from app.research.fetch import fetch_page, fetch_run_sources, is_public
from tests.conftest import alembic_config, needs_db

PAGE = "<html><head><title> Match  report </title><style>p{}</style><script>var x=1</script></head><body>" + (
    "<p>Newcastle beat Arsenal 2-1 at St James' Park on Saturday with two goals in the second half.</p>" * 4
) + "</body></html>"


def resolver(mapping):
    def resolve(host, port, type=None):
        answers = mapping.get(host)
        if answers is None:
            raise socket.gaierror(-2, "Name or service not known")
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, type, 6, "", (a, port)) for a in answers]
    return resolve


PUBLIC = resolver({"example.test": ["93.184.216.34"], "other.test": ["93.184.216.35"],
                   "evil.test": ["10.0.0.5"], "mixed.test": ["93.184.216.34", "127.0.0.1"]})


def html_response(body=PAGE, **headers):
    headers.setdefault("content-type", "text/html; charset=utf-8")
    return httpx2.Response(200, content=body if isinstance(body, bytes) else body.encode(), headers=headers)


def run(url, handler, **kw):
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)
    result = fetch_page(url, resolver=kw.pop("resolver", PUBLIC), transport=httpx2.MockTransport(record), **kw)
    return result, seen


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "100.64.0.1",
    "224.0.0.1", "240.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
    "64:ff9b::7f00:1", "2002:7f00:1::", "2001:0:4136:e378:8000:63bf:3fff:fdd2",
])
def test_non_public_addresses_are_refused(address):
    assert not is_public(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"])
def test_public_addresses_are_allowed(address):
    assert is_public(address)


@pytest.mark.parametrize("url,why", [
    ("ftp://example.test/a", "scheme"), ("file:///etc/passwd", "scheme"), ("javascript:alert(1)", "scheme"),
    ("http://user:pw@example.test/", "user name"), ("http://example.test:8080/", "port 8080"),
    ("https://example.test:22/", "port 22"), ("http:///nohost", "host name"),
])
def test_bad_urls_are_blocked_before_any_lookup(url, why):
    result, seen = run(url, lambda r: html_response())
    assert result.status == "blocked" and why in result.detail and seen == []


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://2130706433/", "http://0x7f.1/", "http://[::1]/",
    "http://169.254.169.254/latest/meta-data/", "http://[::ffff:127.0.0.1]/", "http://0/",
])
def test_private_targets_are_blocked_with_the_real_resolver(url):
    # The real getaddrinfo, which turns numeric spellings of 127.0.0.1 into the address. It does not
    # use the network for these.
    result, seen = run(url, lambda r: html_response(), resolver=socket.getaddrinfo)
    assert result.status == "blocked" and seen == []


@pytest.mark.parametrize("url", ["http://evil.test/", "http://mixed.test/"])
def test_names_that_resolve_to_private_addresses_are_blocked(url):
    result, seen = run(url, lambda r: html_response())  # evil: only private; mixed: one public, one private
    assert result.status == "blocked" and seen == []


def test_connects_to_the_checked_address_with_the_original_host_name():
    result, seen = run("https://example.test/report?id=7", lambda r: html_response())
    assert result.status == "ok" and "Newcastle beat Arsenal" in result.text
    request = seen[0]
    assert request.url.host == "93.184.216.34" and request.url.path == "/report" and request.url.query == b"id=7"
    assert request.headers["host"] == "example.test"
    assert request.extensions["sni_hostname"] == "example.test"


def test_next_address_is_tried_when_the_first_refuses_the_connection():
    two = resolver({"example.test": ["2606:2800:220:1::1", "93.184.216.34"]})  # no IPv6 route, as on some machines

    def handler(request):
        if request.url.host.startswith("2606"):
            raise httpx2.ConnectError("no route", request=request)
        return html_response()
    result, seen = run("https://example.test/", handler, resolver=two)
    assert result.status == "ok" and [r.url.host for r in seen] == ["2606:2800:220:1::1", "93.184.216.34"]


def test_all_addresses_refusing_is_recorded_as_failed():
    def handler(request):
        raise httpx2.ConnectError("refused", request=request)
    result, seen = run("https://example.test/", handler)
    assert result.status == "failed" and "ConnectError" in result.detail


def test_lookup_failure_is_recorded_not_raised():
    result, seen = run("https://nowhere.test/", lambda r: html_response())
    assert result.status == "failed" and "could not look up" in result.detail and seen == []


def test_redirect_to_a_private_address_is_blocked_at_that_hop():
    def handler(request):
        return httpx2.Response(302, headers={"location": "http://evil.test/admin"})
    result, seen = run("https://example.test/", handler)
    assert result.status == "blocked" and "non-public" in result.detail
    assert len(seen) == 1  # the private address was never contacted


def test_relative_redirect_is_followed_and_rechecked():
    def handler(request):
        if request.url.path == "/old":
            return httpx2.Response(301, headers={"location": "/new"})
        return html_response()
    result, seen = run("https://example.test/old", handler)
    assert result.status == "ok" and [r.url.path for r in seen] == ["/old", "/new"]
    assert result.final_url == "https://example.test/new"


def test_redirect_to_another_name_connects_to_that_names_address():
    def handler(request):
        if request.headers["host"] == "example.test":
            return httpx2.Response(302, headers={"location": "https://other.test/x"})
        return html_response()
    result, seen = run("https://example.test/", handler)
    assert result.status == "ok" and seen[1].url.host == "93.184.216.35" and seen[1].headers["host"] == "other.test"


def test_too_many_redirects():
    result, seen = run("https://example.test/", lambda r: httpx2.Response(302, headers={"location": "/again"}))
    assert result.status == "failed" and "redirects" in result.detail and len(seen) == 5


def test_redirect_to_a_bad_scheme_is_blocked():
    result, _ = run("https://example.test/", lambda r: httpx2.Response(302, headers={"location": "file:///etc/passwd"}))
    assert result.status == "blocked"


def test_size_limit_uses_the_decoded_size():
    big = gzip.compress(b"a" * 200_000)  # small on the wire, large once decoded
    assert len(big) < 5_000
    result, _ = run("https://example.test/", lambda r: html_response(big, **{"content-encoding": "gzip"}), max_bytes=50_000)
    assert result.status == "too_large"


def test_declared_size_over_the_limit_is_refused_without_reading():
    result, _ = run("https://example.test/", lambda r: html_response(**{"content-length": "999999999"}), max_bytes=1000)
    assert result.status == "too_large"


@pytest.mark.parametrize("kind", ["application/pdf", "image/png", "application/json", ""])
def test_other_content_types_are_unsupported(kind):
    result, _ = run("https://example.test/", lambda r: httpx2.Response(200, content=b"%PDF", headers={"content-type": kind} if kind else {}))
    assert result.status == "unsupported" and result.text is None


def test_http_errors_are_recorded_with_the_code():
    result, _ = run("https://example.test/", lambda r: httpx2.Response(404))
    assert (result.status, result.http_status) == ("failed", 404)


def test_timeout_is_recorded():
    def handler(request):
        raise httpx2.ReadTimeout("slow", request=request)
    result, _ = run("https://example.test/", handler)
    assert result.status == "failed" and "did not answer" in result.detail


def test_extraction_drops_scripts_styles_and_keeps_the_text():
    title, text = fetch.extract_text(PAGE)
    assert title == "Match report" and "var x" not in text and "p{}" not in text
    assert text.startswith("Newcastle beat Arsenal")


def test_javascript_shell_and_tiny_pages_are_marked_empty_js():
    shell = "<html><head><title>App</title></head><body><div id='root'></div><script src='/app.js'></script><noscript>Please enable JavaScript to run this app.</noscript></body></html>"
    result, _ = run("https://example.test/", lambda r: html_response(shell))
    assert result.status == "empty_js" and result.text is None
    short, _ = run("https://example.test/", lambda r: html_response("<p>Just a few words.</p>"))
    assert short.status == "empty_js"
    msg = "<p>" + "Please enable JavaScript to view this page. " * 3 + "</p>"
    result, _ = run("https://example.test/", lambda r: html_response(msg * 3))
    assert result.status == "empty_js"


def test_plain_text_pages_are_kept():
    body = "Line of the match report. " * 20
    result, _ = run("https://example.test/a.txt", lambda r: httpx2.Response(200, content=body.encode(), headers={"content-type": "text/plain"}))
    assert result.status == "ok" and result.text.startswith("Line of the match report.")


def test_text_is_capped():
    big = "<p>" + ("word " * 100_000) + "</p>"
    result, _ = run("https://example.test/", lambda r: html_response(big), max_bytes=10_000_000)
    assert result.status == "ok" and len(result.text) == fetch.MAX_TEXT_CHARS


def test_unknown_charset_falls_back_to_utf8():
    result, _ = run("https://example.test/", lambda r: html_response(PAGE, **{"content-type": "text/html; charset=nonsense"}))
    assert result.status == "ok"


@needs_db
def test_run_sources_are_fetched_saved_and_capped(fresh_db, monkeypatch):
    command.upgrade(alembic_config(), "head")
    urls = [f"https://example.test/p{i}" for i in range(4)] + ["http://127.0.0.1/secret"]
    with DbSession(fresh_db) as db:
        db.add_all(SourcePage(run_id="r", url=u, retrieved_at=fetch.datetime.now(fetch.UTC), content_hash="h", content="c") for u in urls)
        db.commit()
    settings = load_settings({"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 32,
                              "FETCH_MAX_PAGES_PER_RUN": "4"})
    local = resolver({"example.test": ["93.184.216.34"]})
    def resolve(host, port, type=None):
        return local(host, port, type) if host == "example.test" else [(socket.AF_INET, type, 6, "", (host, port))]
    counts = fetch_run_sources(fresh_db, "r", settings, resolver=resolve, transport=httpx2.MockTransport(lambda r: html_response()))
    assert counts == {"ok": 4}  # the fifth link was beyond the cap and is left alone, visibly
    with DbSession(fresh_db) as db:
        rows = {p.url: p for p in db.query(SourcePage).all()}
    assert rows["https://example.test/p0"].fetch_status == "ok" and "Newcastle" in rows["https://example.test/p0"].page_text
    assert len(rows["https://example.test/p0"].page_text_hash) == 64 and rows["https://example.test/p0"].fetch_method == "plain"
    assert rows["http://127.0.0.1/secret"].fetch_status == "not_fetched"
    # a second call does not fetch the same pages again, and now handles the remaining one (blocked)
    counts = fetch_run_sources(fresh_db, "r", settings, resolver=resolve, transport=httpx2.MockTransport(lambda r: html_response()))
    assert counts == {"blocked": 1}
