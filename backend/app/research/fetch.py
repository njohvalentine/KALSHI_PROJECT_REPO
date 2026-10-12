"""Fetches the pages a run cited, safely, and saves their text (the frozen record for backtests).

The URLs come from a search engine, so they are untrusted: a link could point at this machine, the
database, or a cloud metadata address. Every request therefore goes through the same rules:

1. http or https, port 80 or 443, no user name in the URL.
2. We resolve the host name ourselves and every address must be public.
3. We connect to the address we checked, not to the name again (a name could answer "public" to our
   check and "private" to the connection). The Host header and the TLS name stay the original host.
4. Redirects are followed here, a few at most, and each hop starts again at rule 1.
5. Time and size limits; only text types; the limit applies to the decoded size.

Every outcome is recorded with a status and a short reason. Nothing is skipped silently."""

import hashlib
import ipaddress
import logging
import re
import socket
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx2
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import SourcePage

log = logging.getLogger("app.research.fetch")

USER_AGENT = "valentine-research/0.1 (reads cited pages to check claims; one request per page)"
MAX_REDIRECTS = 4
TOTAL_SECONDS = 25.0
MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 200
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
REDIRECT_CODES = (301, 302, 303, 307, 308)
# Ranges that Python's is_global treats as public but that can wrap a private IPv4 address.
WRAPPED_RANGES = tuple(ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32"))
JS_MESSAGE = re.compile(r"enable javascript|requires javascript|javascript (is )?(disabled|required)", re.I)

Resolver = Callable[..., list]


class Refused(Exception):
    """The fetch must not happen or must stop. `status` is the fetch_status to record."""

    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class FetchResult:
    status: str
    detail: str | None = None
    final_url: str | None = None
    http_status: int | None = None
    text: str | None = None


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not any(ip in net for net in WRAPPED_RANGES if ip.version == 6)


def check_url(url: str) -> tuple[str, str, int, str]:
    """Rule 1. Returns (scheme, host, port, path and query) or raises Refused."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise Refused("blocked", f"scheme {parts.scheme or '(none)'} is not allowed")
    if parts.username is not None or parts.password is not None:
        raise Refused("blocked", "a user name or password in the link is not allowed")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise Refused("blocked", "the port is not a number") from None
    if port not in (80, 443):
        raise Refused("blocked", f"port {port} is not allowed")
    host = parts.hostname
    if not host:
        raise Refused("blocked", "the link has no host name")
    return parts.scheme, host, port, (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def public_addresses(host: str, port: int, resolver: Resolver) -> list[str]:
    """Rule 2. Every address the name resolves to must be public; returns them in the resolver's order."""
    try:
        infos = resolver(host.encode("idna").decode(), port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise Refused("failed", f"could not look up {host}: {exc}") from None
    addresses = [info[4][0].split("%")[0] for info in infos]
    if not addresses:
        raise Refused("failed", f"{host} has no address")
    bad = [a for a in addresses if not is_public(a)]
    if bad:
        raise Refused("blocked", f"{host} points to a non-public address ({bad[0]})")
    return list(dict.fromkeys(addresses))


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def extract_text(html: str) -> tuple[str, str]:
    """Returns (title, visible text). Built-in parser: no script or style, whitespace collapsed."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(parser.parts).split("\n"))
    text = "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", parser.title).strip(), text


def _read_limited(response: httpx2.Response, max_bytes: int, deadline: float) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():  # decoded bytes: the limit also stops decompression bombs
        body.extend(chunk)
        if len(body) > max_bytes:
            raise Refused("too_large", f"the page is larger than {max_bytes} bytes")
        if time.monotonic() > deadline:
            raise Refused("failed", f"the page took longer than {TOTAL_SECONDS:.0f} seconds")
    return bytes(body)


def fetch_page(
    url: str, *, timeout: float = 10.0, max_bytes: int = 2_000_000,
    resolver: Resolver = socket.getaddrinfo, transport: httpx2.BaseTransport | None = None,
) -> FetchResult:
    deadline = time.monotonic() + TOTAL_SECONDS
    current = url
    try:
        for hop in range(MAX_REDIRECTS + 1):
            scheme, host, port, target = check_url(current)
            addresses = public_addresses(host, port, resolver)
            default_port = 443 if scheme == "https" else 80
            headers = {
                "Host": host if port == default_port else f"{host}:{port}",
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
            }
            # Try the checked addresses in order (a laptop or server may have no IPv6 route, for example).
            # A new client per attempt: connections are never reused, so a connection made for one host
            # name is never used for another.
            client = response = None
            connect_error: httpx2.HTTPError | None = None
            for address in addresses:
                literal = f"[{address}]" if ":" in address else address
                client = httpx2.Client(transport=transport, timeout=httpx2.Timeout(timeout), trust_env=False)
                try:
                    request = client.build_request(
                        "GET", f"{scheme}://{literal}:{port}{target}", headers=headers, extensions={"sni_hostname": host}
                    )
                    response = client.send(request, stream=True)
                    break
                except (httpx2.ConnectError, httpx2.ConnectTimeout) as exc:
                    client.close()
                    connect_error = exc
            if response is None:
                raise connect_error  # every checked address refused the connection
            try:
                if response.status_code in REDIRECT_CODES and response.headers.get("location"):
                    if hop == MAX_REDIRECTS:
                        raise Refused("failed", f"more than {MAX_REDIRECTS} redirects")
                    current = urljoin(current, response.headers["location"])
                    continue
                if not response.is_success:
                    return FetchResult("failed", f"the site answered HTTP {response.status_code}", current, response.status_code)
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind not in TEXT_TYPES:
                    return FetchResult("unsupported", f"content type {kind or 'unknown'} cannot be read yet", current, response.status_code)
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise Refused("too_large", f"the page is larger than {max_bytes} bytes")
                raw = _read_limited(response, max_bytes, deadline)
                charset = response.charset_encoding or "utf-8"
            finally:
                response.close()
                client.close()
            try:
                html = raw.decode(charset, errors="replace")
            except LookupError:
                html = raw.decode("utf-8", errors="replace")
            _, text = extract_text(html) if kind != "text/plain" else ("", html.strip())
            if len(text) < MIN_TEXT_CHARS or (len(text) < 1000 and JS_MESSAGE.search(text)):
                return FetchResult("empty_js", f"only {len(text)} characters of text: the page is very short or needs JavaScript", current, response.status_code)
            return FetchResult("ok", None, current, response.status_code, text[:MAX_TEXT_CHARS])
    except Refused as refused:
        return FetchResult(refused.status, refused.detail, current)
    except httpx2.TimeoutException:
        return FetchResult("failed", f"the site did not answer within {timeout:.0f} seconds", current)
    except httpx2.HTTPError as exc:
        return FetchResult("failed", f"{type(exc).__name__}: {exc}"[:300], current)
    raise AssertionError("unreachable")  # the loop always returns, continues or raises


def fetch_run_sources(engine, run_id: str, settings: Settings, **fetch_options) -> dict[str, int]:
    """Fetches the not-yet-fetched pages of a run and saves the outcome on each row. Returns counts by status."""
    with DbSession(engine) as db:
        rows = db.execute(
            select(SourcePage.id, SourcePage.url).where(SourcePage.run_id == run_id, SourcePage.fetch_status == "not_fetched")
            .order_by(SourcePage.id)
        ).all()
    if len(rows) > settings.fetch_max_pages_per_run:
        log.warning(
            "Run %s cited %d pages; fetching the first %d (FETCH_MAX_PAGES_PER_RUN); the rest stay not_fetched",
            run_id, len(rows), settings.fetch_max_pages_per_run,
        )
        rows = rows[: settings.fetch_max_pages_per_run]

    def one(row) -> tuple[int, FetchResult]:
        return row.id, fetch_page(
            row.url, timeout=settings.fetch_timeout_seconds, max_bytes=settings.fetch_max_bytes, **fetch_options
        )

    with ThreadPoolExecutor(max_workers=settings.fetch_concurrency) as pool:
        results = list(pool.map(one, rows))

    counts: dict[str, int] = {}
    now = datetime.now(UTC)
    with DbSession(engine) as db:
        for page_id, result in results:
            page = db.get(SourcePage, page_id)
            page.fetch_status, page.fetch_method, page.fetch_detail = result.status, "plain", result.detail
            page.final_url, page.http_status, page.fetched_at = result.final_url, result.http_status, now
            page.page_text = result.text
            page.page_text_hash = hashlib.sha256(result.text.encode()).hexdigest() if result.text else None
            counts[result.status] = counts.get(result.status, 0) + 1
        db.commit()
    log.info("Run %s: fetched %d page(s): %s", run_id, len(results), counts)
    return counts
