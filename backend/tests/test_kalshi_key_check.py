import base64
import os
import stat

import httpx2
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from app.cli import main
from app.kalshi_key_check import KeyCheckError, run_check, sign, signed_headers, summarize

DEMO = "https://demo.kalshi.test/trade-api/v2"
PROD = "https://prod.kalshi.test/trade-api/v2"


def write_key(tmp_path, key, mode=0o600):
    path = tmp_path / "key.pem"
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    path.chmod(mode)
    return str(path)


def env_for(path, **extra):
    return {"KALSHI_KEY_ID": "key-id-123", "KALSHI_PRIVATE_KEY_PATH": path,
            "KALSHI_DEMO_API_BASE": DEMO, "KALSHI_API_BASE": PROD, **extra}


@pytest.fixture(params=["rsa", "ed25519"])
def key(request):
    if request.param == "rsa":
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return ed25519.Ed25519PrivateKey.generate()


def test_signature_verifies_with_the_public_key(key):
    message = "1700000000000GET/trade-api/v2/portfolio/balance"
    signature = base64.b64decode(sign(key, message))
    if isinstance(key, rsa.RSAPrivateKey):  # raises if the signature or settings are wrong
        key.public_key().verify(signature, message.encode(), padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    else:
        key.public_key().verify(signature, message.encode())


def test_headers_sign_timestamp_method_and_full_path_without_query(key):
    h = signed_headers(key, "kid", "get", "https://x.test/trade-api/v2/portfolio/balance?limit=5", now_ms=1700000000123)
    assert h["KALSHI-ACCESS-KEY"] == "kid" and h["KALSHI-ACCESS-TIMESTAMP"] == "1700000000123"
    expected = "1700000000123GET/trade-api/v2/portfolio/balance"
    signature = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    if isinstance(key, rsa.RSAPrivateKey):
        key.public_key().verify(signature, expected.encode(), padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    else:
        key.public_key().verify(signature, expected.encode())


def mock(handler):
    return httpx2.Client(transport=httpx2.MockTransport(handler))


@pytest.mark.parametrize("accepts,expected", [
    ({"demo.kalshi.test"}, "This key works on: demo."),
    ({"prod.kalshi.test"}, "This key works on: production."),
    ({"demo.kalshi.test", "prod.kalshi.test"}, "This key works on: demo and production."),
    (set(), "This key was rejected by both."),
])
def test_each_environment_is_checked_and_summarised(tmp_path, key, accepts, expected):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.host, request.url.path))
        assert {"kalshi-access-key", "kalshi-access-timestamp", "kalshi-access-signature"} <= set(request.headers)
        return httpx2.Response(200 if request.url.host in accepts else 401, json={"balance": 12345})

    results, _ = run_check(env_for(write_key(tmp_path, key)), client=mock(handler))
    assert calls == [("GET", "demo.kalshi.test", "/trade-api/v2/portfolio/balance"),
                     ("GET", "prod.kalshi.test", "/trade-api/v2/portfolio/balance")]  # read-only, balance only
    assert summarize(results).startswith(expected)


def test_connection_problem_is_reported_not_hidden(tmp_path, key):
    def handler(request):
        raise httpx2.ConnectError("boom")

    results, _ = run_check(env_for(write_key(tmp_path, key)), client=mock(handler))
    assert all(r.status == "unknown" and "could not connect" in r.detail for r in results)
    assert summarize(results).startswith("Could not tell")


def test_missing_settings_and_bad_key_files_are_clear_errors(tmp_path):
    with pytest.raises(KeyCheckError, match="KALSHI_KEY_ID"):
        run_check({"KALSHI_PRIVATE_KEY_PATH": "x", "KALSHI_DEMO_API_BASE": DEMO, "KALSHI_API_BASE": PROD})
    with pytest.raises(KeyCheckError, match="Cannot read"):
        run_check(env_for(str(tmp_path / "nope.pem")))
    bad = tmp_path / "bad.pem"
    bad.write_text("not a key")
    with pytest.raises(KeyCheckError, match="not a readable"):
        run_check(env_for(str(bad)))


def test_loose_file_permissions_warn(tmp_path):
    k = ed25519.Ed25519PrivateKey.generate()
    _, warnings = run_check(env_for(write_key(tmp_path, k, mode=0o644)), client=mock(lambda r: httpx2.Response(401)))
    assert warnings and "chmod 600" in warnings[0]
    _, warnings = run_check(env_for(write_key(tmp_path, k, mode=0o600)), client=mock(lambda r: httpx2.Response(401)))
    assert warnings == []


def test_output_never_contains_the_key_signature_or_balance(tmp_path, capsys, monkeypatch, key):
    path = write_key(tmp_path, key)
    pem_body = open(path).read().splitlines()[1]
    seen = {}

    def handler(request):
        seen["sig"] = request.headers["kalshi-access-signature"]
        return httpx2.Response(200, json={"balance": 987654321})

    real_client = httpx2.Client
    monkeypatch.setattr("app.kalshi_key_check.httpx2.Client", lambda **kw: real_client(transport=httpx2.MockTransport(handler)))
    for name, value in env_for(path).items():
        monkeypatch.setenv(name, value)
    assert main(["check-kalshi-key"]) == 0
    out = capsys.readouterr()
    text = out.out + out.err
    assert "demo: accepted" in text and "production: accepted" in text
    assert pem_body not in text and seen["sig"] not in text and "987654321" not in text and "key-id-123" not in text
    assert "DATABASE_URL" not in text  # this command does not need the database
