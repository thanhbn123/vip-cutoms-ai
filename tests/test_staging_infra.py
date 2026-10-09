"""Staging infra regression tests (G15C).

Real staging exposed two defects that these tests lock down:

1. `infra/staging/Caddyfile` passed TLS_MODE straight into the Caddy `tls` directive. Caddy v2
   accepts only `internal`, `force_automate` or an email address there, so the two documented
   modes `off` and `acme` aborted config adaptation and the proxy container never started.
2. `scripts/staging/deploy.sh` aborts with a message pointing at
   `infra/staging/.env.staging.example`, which did not exist in the repository.

These live outside apps/api/tests because they assert on infrastructure files and need no
database; no Docker is required either — the mapping shipped in the compose entrypoint is
executed with /bin/sh.
"""

import pathlib
import re
import subprocess
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
STAGING = REPO / "infra" / "staging"
CADDYFILE = STAGING / "Caddyfile"
COMPOSE = STAGING / "docker-compose.staging.yml"
ENV_EXAMPLE = STAGING / ".env.staging.example"

# Caddy v2: `tls` takes exactly one of these as a single argument.
VALID_TLS_ARGS = {"internal", "force_automate"}


def _proxy_command() -> str:
    """The shell snippet the proxy service runs, read straight from the compose file.

    Parsed textually rather than with a YAML library so the test suite needs no extra
    dependency: the snippet is the `command:` block literal inside the `proxy:` service.
    """
    compose = COMPOSE.read_text()
    proxy = re.search(r"^  proxy:\n(.*?)(?=^  \w|\Z)", compose, re.M | re.S)
    assert proxy, "proxy service not found in docker-compose.staging.yml"
    body = proxy.group(1)
    assert 'entrypoint: ["/bin/sh", "-c"]' in body, "proxy must run its mapping through /bin/sh"
    block = re.search(r"^    command:\n      - \|\n(.*?)(?=^    \w|\Z)", body, re.M | re.S)
    assert block, "proxy command must be a single `- |` block literal"
    return textwrap.dedent(block.group(1))


def _resolve(tls_mode: str, public_host: str = "staging.example.internal"):
    """Run the shipped mapping and return (returncode, SITE_ADDRESS, TLS_ARG)."""
    # Replace the `exec caddy run ...` line with an echo so nothing needs the caddy binary.
    snippet = re.sub(r"^\s*exec caddy run .*$", 'echo "$SITE_ADDRESS|$TLS_ARG"', _proxy_command(), flags=re.M)
    # Compose escapes `$` as `$$` for its own interpolation; the container sees single `$`.
    snippet = snippet.replace("$$", "$")
    proc = subprocess.run(
        ["/bin/sh", "-c", snippet],
        env={"TLS_MODE": tls_mode, "PUBLIC_HOST": public_host, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    resolved = [ln for ln in proc.stdout.splitlines() if "|" in ln]
    if not resolved:
        return proc.returncode, None, None
    site_address, tls_arg = resolved[-1].split("|", 1)
    return proc.returncode, site_address, tls_arg


# --- defect 1: TLS_MODE must never reach the `tls` directive raw ---------------------------


def test_caddyfile_does_not_pass_tls_mode_to_tls_directive():
    text = CADDYFILE.read_text()
    assert "tls {$TLS_MODE}" not in text, "TLS_MODE must be translated, not passed to `tls` directly"
    assert re.search(r"^\ttls \{\$TLS_ARG:internal\}$", text, re.M), "tls must read TLS_ARG"
    assert re.search(r"^\{\$SITE_ADDRESS\}", text, re.M), "site address must come from SITE_ADDRESS"


@pytest.mark.parametrize(
    ("tls_mode", "site_address", "tls_arg"),
    [
        ("internal", "https://staging.example.internal", "internal"),
        ("acme", "staging.example.internal", "force_automate"),
        ("off", "http://staging.example.internal", "internal"),
        ("ops@example.com", "staging.example.internal", "ops@example.com"),
    ],
)
def test_every_documented_tls_mode_resolves(tls_mode, site_address, tls_arg):
    code, got_address, got_arg = _resolve(tls_mode)
    assert code == 0, f"TLS_MODE={tls_mode} must be accepted"
    assert got_address == site_address
    assert got_arg == tls_arg


@pytest.mark.parametrize("tls_mode", ["internal", "acme", "off", "ops@example.com"])
def test_resolved_tls_arg_is_valid_caddy_v2_syntax(tls_mode):
    """`off`/`acme` previously produced `tls off`/`tls acme`, which Caddy rejects."""
    _, _, tls_arg = _resolve(tls_mode)
    assert tls_arg in VALID_TLS_ARGS or "@" in tls_arg, f"`tls {tls_arg}` is not valid Caddy v2 syntax"


def test_off_mode_uses_http_scheme_so_automatic_https_is_disabled():
    _, site_address, _ = _resolve("off")
    assert site_address.startswith("http://"), "upstream-TLS mode must not let Caddy claim 443/ACME"


@pytest.mark.parametrize("tls_mode", ["", "on", "selfsigned", "acme ", "not-an-email@"])
def test_unknown_tls_mode_fails_fast(tls_mode):
    code, _, _ = _resolve(tls_mode)
    assert code != 0, f"TLS_MODE={tls_mode!r} must be rejected, not silently mis-adapted"


def test_tls_modes_documented_in_caddyfile_match_the_implementation():
    documented = set(re.findall(r"^#\s+TLS_MODE=(\S+)", CADDYFILE.read_text(), re.M))
    assert documented == {"internal", "acme", "off", "<email>"}


# --- defect 2: the env template deploy.sh points at must exist ----------------------------


def test_deploy_script_env_template_exists():
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} is referenced by scripts/staging/deploy.sh"


def test_env_template_is_tracked_by_git_but_real_env_is_ignored():
    def ignored(path: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO).returncode == 0

    assert not ignored("infra/staging/.env.staging.example"), "the template must be committable"
    assert ignored("infra/staging/.env"), "the real staging env file must stay git-ignored"


def test_env_template_covers_every_key_deploy_and_compose_require():
    keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(), re.M))
    # Hard-required by docker-compose.staging.yml (`${VAR:?}`) and checked by deploy.sh.
    required = {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "APP_SECRET_KEY",
        "PUBLIC_HOST",
        "PUBLIC_WEB_ORIGIN",
        "AI_PROVIDER",
        "TLS_MODE",
        "SEED_DEMO_PASSWORD",
    }
    assert required <= keys, f"missing from template: {sorted(required - keys)}"


def test_env_template_ships_no_secret_values():
    for line in ENV_EXAMPLE.read_text().splitlines():
        if not re.match(r"^[A-Z][A-Z0-9_]*=", line):
            continue
        key, _, value = line.partition("=")
        if key in {"POSTGRES_PASSWORD", "APP_SECRET_KEY", "SEED_DEMO_PASSWORD"}:
            assert value == "", f"{key} must ship empty, got a value"


def test_env_template_defaults_to_mock_ai_provider():
    assert re.search(r"^AI_PROVIDER=mock$", ENV_EXAMPLE.read_text(), re.M)
