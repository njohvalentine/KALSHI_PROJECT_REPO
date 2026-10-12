"""Tells whether a Kalshi API key works on the demo site, the production site, both or neither.

It only sends one read-only request (GET /portfolio/balance) and never an order. It prints
"accepted" or "rejected" per environment and never prints the key, the signature or the balance.
Signing follows Kalshi's docs (Quick Start: Authenticated Requests): the signed text is
timestamp-in-milliseconds + HTTP method + full path from the API root without the query string;
RSA keys use RSA-PSS with SHA-256 (salt length = digest length), Ed25519 keys sign the text directly;
the signature is base64. The parsed key type decides the algorithm, not the file header.
"""

import base64
import os
import stat
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

REQUIRED = ("KALSHI_KEY_ID", "KALSHI_PRIVATE_KEY_PATH", "KALSHI_DEMO_API_BASE", "KALSHI_API_BASE")


class KeyCheckError(Exception):
    """The check cannot run (missing setting, unreadable or unsupported key file)."""


@dataclass(frozen=True)
class EnvironmentResult:
    name: str
    status: str  # "accepted", "rejected" or "unknown"
    detail: str = ""


def load_private_key(path: str):
    try:
        data = open(path, "rb").read()
    except OSError as exc:
        raise KeyCheckError(f"Cannot read the private key file: {exc.strerror}") from exc
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except (ValueError, TypeError) as exc:
        raise KeyCheckError("The private key file is not a readable unencrypted PEM key") from exc
    if not isinstance(key, (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)):
        raise KeyCheckError("Only RSA and Ed25519 keys are supported (as in Kalshi's docs)")
    return key


def sign(private_key, message: str) -> str:
    data = message.encode()
    if isinstance(private_key, rsa.RSAPrivateKey):
        signature = private_key.sign(
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    else:
        signature = private_key.sign(data)
    return base64.b64encode(signature).decode()


def signed_headers(private_key, key_id: str, method: str, url: str, *, now_ms: int | None = None) -> dict[str, str]:
    timestamp = str(now_ms if now_ms is not None else int(time.time() * 1000))
    path = urlparse(url).path  # full path from the root, query string already excluded
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": sign(private_key, timestamp + method.upper() + path),
    }


def check_environment(name: str, base_url: str, private_key, key_id: str, client: httpx2.Client) -> EnvironmentResult:
    url = f"{base_url.rstrip('/')}/portfolio/balance"
    try:
        response = client.get(url, headers=signed_headers(private_key, key_id, "GET", url))
    except httpx2.TransportError as exc:
        return EnvironmentResult(name, "unknown", f"could not connect ({type(exc).__name__})")
    if response.status_code == 200:
        return EnvironmentResult(name, "accepted")
    if response.status_code in (401, 403):
        return EnvironmentResult(name, "rejected", f"HTTP {response.status_code}")
    return EnvironmentResult(name, "unknown", f"unexpected HTTP {response.status_code}")


def run_check(env: Mapping[str, str], client: httpx2.Client | None = None) -> tuple[list[EnvironmentResult], list[str]]:
    """Returns the per-environment results and any warnings."""
    missing = [name for name in REQUIRED if not env.get(name, "").strip()]
    if missing:
        raise KeyCheckError("Missing settings: " + ", ".join(missing))
    key_path = env["KALSHI_PRIVATE_KEY_PATH"].strip()
    private_key = load_private_key(key_path)
    warnings = []
    if os.stat(key_path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        warnings.append("The private key file can be read by other users. Restrict it (chmod 600).")
    owns_client = client is None
    client = client or httpx2.Client(timeout=httpx2.Timeout(10.0, connect=3.0))
    try:
        key_id = env["KALSHI_KEY_ID"].strip()
        results = [
            check_environment("demo", env["KALSHI_DEMO_API_BASE"], private_key, key_id, client),
            check_environment("production", env["KALSHI_API_BASE"], private_key, key_id, client),
        ]
    finally:
        if owns_client:
            client.close()
    return results, warnings


def summarize(results: list[EnvironmentResult]) -> str:
    accepted = [r.name for r in results if r.status == "accepted"]
    if accepted:
        return "This key works on: " + " and ".join(accepted) + "."
    if any(r.status == "unknown" for r in results):
        return "Could not tell: at least one environment could not be checked (see above)."
    return "This key was rejected by both. The key ID or private key is wrong, or the pair is incomplete."
