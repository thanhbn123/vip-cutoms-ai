"""Production config/runbook contract tests (G16).

The production files are templates for a deployment that has deliberately NOT happened, so
there is no running stack to test against. What can still be tested — and what these tests
cover — are the invariants that would make the templates dangerous if they drifted:

1. The templates must never contain a real secret, and must never grow a key for a provider
   or integration this build does not implement (product rules #1 and #7, no fabricated
   provider support).
2. `docker-compose.production.yml` is an OVERLAY on the staging compose. A service name typo
   in an overlay does not fail loudly — compose happily defines a new, broken service — so
   the service names are asserted against the staging file.
3. The one-shot `migrate` service must never inherit a restart policy.

These live outside apps/api/tests because they assert on infrastructure files and need no
database and no Docker.
"""

import pathlib
import re
import stat
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
PROD = REPO / "infra" / "production"
ENV_EXAMPLE = PROD / ".env.production.example"
OVERLAY = PROD / "docker-compose.production.yml"
STAGING_COMPOSE = REPO / "infra" / "staging" / "docker-compose.staging.yml"
BACKUP = REPO / "scripts" / "production" / "backup.sh"
UNIT = PROD / "vip-customs-backup.service"
TIMER = PROD / "vip-customs-backup.timer"

# Providers actually implemented in this build (app/ai/gateway.py, app/storage/base.py).
IMPLEMENTED_AI_PROVIDERS = {"mock"}
IMPLEMENTED_STORAGE_PROVIDERS = {"local"}
# Modes the shipped Caddy mapping in docker-compose.staging.yml accepts.
VALID_TLS_MODES = {"internal", "acme", "off"}


def _env(path: pathlib.Path = ENV_EXAMPLE) -> dict[str, str]:
    """Parse KEY=VALUE lines, ignoring comments and blanks."""
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


@pytest.mark.parametrize("path", [ENV_EXAMPLE, OVERLAY, BACKUP, UNIT, TIMER])
def test_production_artifacts_exist(path):
    assert path.is_file(), f"{path.relative_to(REPO)} is missing"


@pytest.mark.parametrize("path", [ENV_EXAMPLE, OVERLAY, BACKUP, UNIT, TIMER])
def test_production_artifacts_are_tracked_by_git(path):
    """Found the hard way: `.gitignore`'s `.env.*` rule swallowed .env.production.example.

    The existing `!*.env.example` negation does not match `.env.production.example` — that
    name does not end in `.env.example` — so the template was present locally, passed every
    test in the working tree, and was simply absent from the commit. A clean checkout is the
    only place that shows up, so assert tracking directly.
    """
    rel = str(path.relative_to(REPO))
    # --no-index is required: git skips exclusion rules for files already in the index, so
    # without it this assertion would pass on a tracked file no matter what .gitignore says,
    # and would not catch the pattern regressing for the next new file.
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "-q", rel], cwd=REPO).returncode == 0
    assert not ignored, f"{rel} is matched by a .gitignore pattern and would never reach a deployment"
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO,
                             capture_output=True).returncode == 0
    assert tracked, f"{rel} is not tracked by git"


def test_the_real_production_env_file_stays_ignored():
    """The negation added for the template must not expose the filled-in file next to it."""
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "-q", "infra/production/.env"], cwd=REPO).returncode == 0
    assert ignored, "infra/production/.env must stay git-ignored — it holds real secrets"


def test_secret_bearing_keys_are_empty_placeholders():
    """A template with a filled-in secret is how secrets get committed."""
    env = _env()
    for key in ("POSTGRES_PASSWORD", "APP_SECRET_KEY"):
        assert key in env, f"{key} must be present so the operator knows it is required"
        assert env[key] == "", f"{key} must be an empty placeholder, found a value"


def test_required_deploy_keys_are_documented():
    env = _env()
    for key in ("APP_ENV", "POSTGRES_USER", "POSTGRES_DB", "PUBLIC_HOST", "PUBLIC_WEB_ORIGIN"):
        assert key in env, f"{key} missing from the production template"
    assert env["APP_ENV"] == "production"


def test_template_only_names_implemented_providers():
    """Guards against a fabricated provider (e.g. AI_PROVIDER=openai) appearing in the template.

    The gateway fails closed on any other value, so such a template would produce a stack
    whose /ready is permanently 503 — a confusing way to discover B-01 is still open.
    """
    env = _env()
    assert env["AI_PROVIDER"] in IMPLEMENTED_AI_PROVIDERS
    assert env["OBJECT_STORAGE_PROVIDER"] in IMPLEMENTED_STORAGE_PROVIDERS


def test_template_has_no_customs_integration_or_demo_seed_keys():
    """Product rule #7: no customs submission path exists, so no key may imply one.

    SEED_DEMO_PASSWORD is excluded too: seed_demo.py refuses to run outside development/test,
    so a production template offering it would be misleading.
    """
    env = _env()
    assert "SEED_DEMO_PASSWORD" not in env, "demo seeding is not part of a production config"
    forbidden = re.compile(r"VNACCS|ECUS|CUSTOMS_(API|ENDPOINT|URL|TOKEN|CERT)|SUBMIT_", re.I)
    for key in env:
        assert not forbidden.search(key), f"{key} implies a customs integration that does not exist"


def test_template_tls_mode_is_a_mode_the_proxy_accepts():
    mode = _env()["TLS_MODE"]
    assert mode in VALID_TLS_MODES or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", mode), (
        f"TLS_MODE={mode} would abort Caddy config adaptation"
    )


def test_template_does_not_pin_image_tag_to_latest():
    """An unpinned tag makes a rollback ambiguous: `latest` is whatever was last built."""
    assert _env()["IMAGE_TAG"] != "latest"


def _services(path: pathlib.Path) -> set[str]:
    """Top-level service names, parsed textually so the suite needs no YAML dependency."""
    body = re.search(r"^services:\n(.*?)(?=^\w|\Z)", path.read_text(), re.M | re.S)
    assert body, f"no services block in {path.name}"
    return set(re.findall(r"^  ([a-z][a-z0-9_-]*):", body.group(1), re.M))


def test_overlay_services_all_exist_in_the_staging_compose():
    """A typo'd service name in an overlay silently defines a new service instead of failing."""
    extra = _services(OVERLAY) - _services(STAGING_COMPOSE)
    assert not extra, f"overlay defines services absent from the staging compose: {sorted(extra)}"


def test_overlay_uses_a_distinct_project_name():
    """Sharing a compose project name would make a production stack reuse staging volumes."""
    prod = re.search(r"^name:\s*(\S+)", OVERLAY.read_text(), re.M)
    staging = re.search(r"^name:\s*(\S+)", STAGING_COMPOSE.read_text(), re.M)
    assert prod and staging and prod.group(1) != staging.group(1)


def test_overlay_never_gives_the_one_shot_migrate_service_a_restart_policy():
    """`restart: always` on the migration service would re-run it in a loop on failure."""
    block = re.search(r"^  migrate:\n(.*?)(?=^  \w|\Z)", OVERLAY.read_text(), re.M | re.S)
    assert block, "migrate service missing from the overlay"
    assert not re.search(r"^\s+restart:", block.group(1), re.M), "migrate must not be restarted"


@pytest.mark.parametrize("service", ["postgres", "api", "web", "proxy"])
def test_overlay_bounds_logs_for_every_long_running_service(service):
    """Unbounded json-file logs are the most common way a long-lived host fills its disk."""
    block = re.search(rf"^  {service}:\n(.*?)(?=^  \w|\Z)", OVERLAY.read_text(), re.M | re.S)
    assert block and "logging:" in block.group(1), f"{service} has no logging configuration"


def test_overlay_adds_the_web_healthcheck_staging_lacks():
    """Without it a dead static-file container reports Up while the proxy serves 502."""
    block = re.search(r"^  web:\n(.*?)(?=^  \w|\Z)", OVERLAY.read_text(), re.M | re.S)
    assert block and "healthcheck:" in block.group(1)


def test_backup_script_is_executable_and_syntactically_valid():
    assert BACKUP.stat().st_mode & stat.S_IXUSR, "backup.sh must be executable"
    assert subprocess.run(["bash", "-n", str(BACKUP)], capture_output=True).returncode == 0


def test_backup_script_refuses_to_run_without_a_config_file(tmp_path):
    """It must fail loudly, not report a successful no-op backup."""
    proc = subprocess.run(
        ["bash", str(BACKUP)],
        env={"DEPLOY_PATH": str(tmp_path), "ENV_FILE": "does-not-exist.env", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "env file" in proc.stderr.lower()


def test_backup_script_backs_up_uploads_as_well_as_the_database():
    """The DB holds only storage keys, so a database-only backup restores broken documents."""
    body = BACKUP.read_text()
    assert "pg_dump" in body and "uploads" in body
    assert "sha256sum" in body, "artifacts need checksums to detect silent truncation"


def test_backup_script_never_prints_the_env_file():
    body = BACKUP.read_text()
    assert not re.search(r"^\s*(cat|echo)\s+.*\$ENV_FILE", body, re.M)
    assert not re.search(r'^\s*(cat|echo)\s+.*"\$\{?ENV_FILE', body, re.M)


def test_systemd_units_point_at_files_that_exist_and_reference_each_other():
    unit, timer = UNIT.read_text(), TIMER.read_text()
    exec_start = re.search(r"^ExecStart=.*?bash\s+(\S+)", unit, re.M)
    assert exec_start, "service has no ExecStart invoking a script"
    assert (REPO / exec_start.group(1)).is_file(), f"{exec_start.group(1)} does not exist"
    assert f"Unit={UNIT.name}" in timer, "timer must reference the service unit"
    assert "Persistent=true" in timer, "a missed nightly backup must still run"
    assert "Type=oneshot" in unit
