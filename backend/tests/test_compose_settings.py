"""docker-compose.yml must hand every setting the backend reads to the container, and must not repeat the defaults (they live in config.py).

A setting that the compose file does not list never reaches the container from .env, silently; a default repeated there overrides the code's own.
Both happened (twelve settings missing; MAX_RESEARCHERS 4 against 3), because no test looked across the two files."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = (ROOT / "backend" / "app" / "config.py").read_text()
COMPOSE = (ROOT / "docker-compose.yml").read_text()


def settings_read(config_text: str) -> set[str]:
    return set(re.findall(r'env(?:\.get\(|\[)\s*"([A-Z][A-Z_0-9]+)"', config_text)) | set(re.findall(r'_parse_[a-z_]+\(\s*"([A-Z][A-Z_0-9]+)"', config_text))


def backend_environment(compose_text: str) -> list[str]:
    block = compose_text[compose_text.index("  backend:"):]
    block = block[:block.index("    depends_on:")]
    return [line for line in block.splitlines() if re.match(r"^      [A-Z][A-Z_0-9]+:", line)]


def test_every_setting_the_backend_reads_is_passed_to_the_container():
    passed = {re.match(r"^      ([A-Z_0-9]+):", line).group(1) for line in backend_environment(COMPOSE)}
    assert len(settings_read(CONFIG)) > 70  # the pattern really finds the settings
    missing = sorted(settings_read(CONFIG) - passed)
    assert not missing, f"config.py reads these settings but docker-compose.yml does not pass them, so a value in .env never reaches the backend: {missing}"


def test_the_compose_file_repeats_no_default_the_code_has_one():
    repeated = [line.strip() for line in backend_environment(COMPOSE) if ":-" in line]
    assert not repeated, f"defaults live in config.py only; remove them from docker-compose.yml: {repeated}"


def test_the_checks_would_have_caught_the_old_file():
    """The same two checks on the compose file as it was before the fix (kept as text here so the test proves it can fail)."""
    old = "  backend:\n    environment:\n      DATABASE_URL: x\n      MAX_RESEARCHERS: ${MAX_RESEARCHERS:-4}\n    depends_on:\n"
    assert [line for line in backend_environment(old) if ":-" in line]
    assert "RESEARCH_MAX_PER_DAY" not in {re.match(r"^      ([A-Z_0-9]+):", line).group(1) for line in backend_environment(old)}
