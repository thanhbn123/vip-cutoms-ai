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
IMPLEMENTED_AI_PROVIDERS = {"mock", "http-llm"}  # G18: http-llm is the vendor-neutral real adapter
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
    for key in ("POSTGRES_PASSWORD", "APP_SECRET_KEY", "AI_PROVIDER_API_KEY", "OFFSITE_TARGET"):
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


# ──────────────────────────────────────────────────────────────────────────────────────────────
# Execution tests for scripts/production/backup.sh.
#
# A dump holds every customer document and audit record in plaintext, so the permissions it
# creates are a security property and are asserted by actually running the script — reading the
# source for the string "umask 077" would not prove the artifacts end up 0600.
#
# `docker` is mocked, so nothing touches a real stack, a real database or real data. Every run
# happens inside pytest's tmp_path, and the deliberately hostile umask 022 (which would
# otherwise yield world-readable 0644 dumps) is set for the subprocess.
#
# Scope limit, stated so the coverage is not overread: these tests pin the END STATE — mode 600
# artifacts and a mode 700 directory. They do not isolate `umask 077` from the explicit chmods;
# removing the umask line alone keeps them green, because the chmods still correct the mode.
# The umask is nonetheless not redundant: it closes the window between a file being created and
# being chmod-ed, during which it would otherwise exist as 0644. A test cannot observe that race
# from outside the process, so it is defence-in-depth that rests on review, not on these tests.
# ──────────────────────────────────────────────────────────────────────────────────────────────

FAKE_DUMP = b"PGDMP-fake-not-a-real-dump\n"
FAKE_TGZ = b"\x1f\x8b-fake-not-a-real-archive\n"

# Mock `docker`, dispatching on the full argument string the script builds. Every invocation is
# appended to $DOCKER_CALL_LOG so the tests can assert on *how* the script used docker, not just
# on its output.
#
#   <compose…> ps -q postgres        -> a container id, so the "is it running" probe passes
#   <compose…> config --images api   -> the api image name, for the pre-flight
#   image inspect <name>             -> success, i.e. the image is present locally
#   <compose…> exec -T postgres …    -> dump bytes on stdout
#   <compose…> run --rm --no-deps …  -> archive bytes on stdout (the one-off reader)
#   <compose…> exec -T api …         -> FAILS, modelling a STOPPED api container. The script
#                                       must never take this path; `exec` cannot work during
#                                       the quiesced procedure, which stops api and web.
FAKE_DOCKER = r"""#!/bin/sh
echo "$*" >> "$DOCKER_CALL_LOG"
case "$*" in
  *"ps -q postgres"*)       echo fakecontainerid ;;
  *"config --images api"*)  echo '__IMAGE__' ;;
  "image inspect"*)         __IMAGE_INSPECT__ ;;
  *"exec -T postgres"*)     printf '%s' '__DUMP__' ;;
  *"run --rm --no-deps"*)   printf '%s' '__TGZ__' ;;
  *"exec -T api"*)
      echo "Error response from daemon: container for service "api" is not running" >&2
      exit 1 ;;
  *) echo "fake docker: unexpected invocation: $*" >&2; exit 2 ;;
esac
"""


def _backup_sandbox(tmp_path, *, dump="PGDMP-fake-not-a-real-dump", tgz="GZIP-fake-not-a-real-archive",
                    retention="14", backup_dir=None, image="vip-customs-api:testtag",
                    image_present=True):
    """Build an isolated DEPLOY_PATH + env file + mocked `docker` on PATH."""
    deploy = tmp_path / "deploy"
    (deploy / "infra" / "production").mkdir(parents=True)
    backups = backup_dir if backup_dir is not None else tmp_path / "backups"
    (deploy / "infra" / "production" / ".env").write_text(
        f"BACKUP_DIR={backups}\nBACKUP_RETENTION_DAYS={retention}\n"
        "POSTGRES_USER=unused\nPOSTGRES_DB=unused\n"
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(
        FAKE_DOCKER.replace("__DUMP__", dump).replace("__TGZ__", tgz).replace("__IMAGE__", image)
        .replace("__IMAGE_INSPECT__", "exit 0" if image_present else "exit 1")
    )
    docker.chmod(0o755)
    return deploy, pathlib.Path(str(backups)), bindir


def _run_backup(deploy, bindir, umask="022"):
    """Run the real script with the mocked docker, under a deliberately permissive umask."""
    # `umask 022` in the wrapper is the point of the test: it is what a cron job or an
    # interactive shell would hand the script, and it must not leak into the artifacts.
    return subprocess.run(
        ["/bin/sh", "-c", f'umask {umask}; exec bash "{BACKUP}"'],
        cwd=str(deploy),
        env={
            "DEPLOY_PATH": str(deploy),
            "ENV_FILE": "infra/production/.env",
            "PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(deploy),
            "DOCKER_CALL_LOG": str(pathlib.Path(deploy).parent / "docker-calls.log"),
        },
        capture_output=True, text=True,
    )


def _mode(path: pathlib.Path) -> str:
    return oct(path.stat().st_mode & 0o777)[2:]


def _docker_calls(tmp_path) -> list[str]:
    log = tmp_path / "docker-calls.log"
    return log.read_text().splitlines() if log.exists() else []


def test_backup_run_creates_private_artifacts_despite_a_permissive_umask(tmp_path):
    """The whole point: under umask 022 these would default to 0644 (world-readable)."""
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    proc = _run_backup(deploy, bindir, umask="022")
    assert proc.returncode == 0, f"backup failed:\n{proc.stdout}\n{proc.stderr}"

    dumps = list(backups.glob("db-*.dump"))
    archives = list(backups.glob("uploads-*.tgz"))
    assert len(dumps) == 1 and len(archives) == 1, f"unexpected artifacts: {list(backups.iterdir())}"

    for artifact in [dumps[0], archives[0], backups / f"{dumps[0].name}.sha256",
                     backups / f"{archives[0].name}.sha256", backups / "MANIFEST.txt"]:
        assert artifact.is_file(), f"{artifact.name} was not created"
        assert _mode(artifact) == "600", f"{artifact.name} is mode {_mode(artifact)}, expected 600"


def test_backup_run_secures_the_backup_directory_to_700(tmp_path):
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    assert _run_backup(deploy, bindir, umask="022").returncode == 0
    assert _mode(backups) == "700", f"BACKUP_DIR is mode {_mode(backups)}, expected 700"


def test_backup_run_tightens_a_preexisting_world_readable_directory_and_manifest(tmp_path):
    """Appending to an existing MANIFEST.txt keeps its old mode, so it is chmod-ed every run."""
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    backups.mkdir(parents=True)
    backups.chmod(0o755)
    manifest = backups / "MANIFEST.txt"
    manifest.write_text("2026-01-01 earlier-run\n")
    manifest.chmod(0o644)

    assert _run_backup(deploy, bindir, umask="022").returncode == 0
    assert _mode(backups) == "700", "a pre-existing loose directory must be tightened"
    assert _mode(manifest) == "600", "a pre-existing loose manifest must be tightened"
    assert "earlier-run" in manifest.read_text(), "the manifest must be appended to, not replaced"
    assert len(manifest.read_text().strip().splitlines()) == 2


def test_backup_run_records_both_artifacts_and_the_non_atomic_nature_in_the_manifest(tmp_path):
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    assert _run_backup(deploy, bindir).returncode == 0
    line = (backups / "MANIFEST.txt").read_text().strip()
    assert "db=" in line and "uploads=" in line
    assert "not_atomic=sequential" in line, "the manifest must not imply a coherent snapshot"


def test_backup_run_checksums_match_the_bytes_written(tmp_path):
    """A checksum that does not match its artifact makes the whole exercise pointless."""
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    assert _run_backup(deploy, bindir).returncode == 0
    for artifact in list(backups.glob("db-*.dump")) + list(backups.glob("uploads-*.tgz")):
        recorded = (backups / f"{artifact.name}.sha256").read_text().split()[0]
        import hashlib
        assert recorded == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_backup_refuses_when_the_backup_dir_is_a_symlink(tmp_path):
    """Otherwise every dump is redirected to a path someone else chose, and chmod 700 follows it."""
    elsewhere = tmp_path / "attacker-controlled"
    elsewhere.mkdir()
    link = tmp_path / "backups-link"
    link.symlink_to(elsewhere, target_is_directory=True)
    deploy, _, bindir = _backup_sandbox(tmp_path, backup_dir=link)

    proc = _run_backup(deploy, bindir)
    assert proc.returncode != 0, "a symlinked BACKUP_DIR must be refused"
    assert "symlink" in proc.stderr.lower()
    assert not list(elsewhere.iterdir()), "nothing may be written through the symlink"


def test_backup_refuses_when_the_backup_dir_path_is_a_regular_file(tmp_path):
    occupied = tmp_path / "backups-is-a-file"
    occupied.write_text("not a directory")
    deploy, _, bindir = _backup_sandbox(tmp_path, backup_dir=occupied)

    proc = _run_backup(deploy, bindir)
    assert proc.returncode != 0
    assert "not a directory" in proc.stderr.lower()


def test_backup_refuses_a_non_integer_retention(tmp_path):
    """`find -mtime +<garbage>` would otherwise fail obscurely, mid-run, after writing dumps."""
    deploy, _, bindir = _backup_sandbox(tmp_path, retention="not-a-number")
    proc = _run_backup(deploy, bindir)
    assert proc.returncode != 0
    assert "integer" in proc.stderr.lower()


def test_backup_fails_loudly_on_an_empty_dump_instead_of_reporting_success(tmp_path):
    """An empty dump that exits 0 is the worst outcome: a backup job that is silently useless."""
    deploy, backups, bindir = _backup_sandbox(tmp_path, dump="")
    proc = _run_backup(deploy, bindir)
    assert proc.returncode != 0
    assert "empty" in proc.stderr.lower()
    assert not (backups / "MANIFEST.txt").exists(), "a failed run must not be recorded as taken"


def test_backup_fails_loudly_on_an_empty_uploads_archive(tmp_path):
    deploy, backups, bindir = _backup_sandbox(tmp_path, tgz="")
    proc = _run_backup(deploy, bindir)
    assert proc.returncode != 0
    assert "empty" in proc.stderr.lower()
    assert not (backups / "MANIFEST.txt").exists()


def test_backup_retention_prunes_only_its_own_stale_artifacts(tmp_path):
    """Must not delete the manifest, a fresh backup, or anything it did not create."""
    deploy, backups, bindir = _backup_sandbox(tmp_path, retention="1")
    backups.mkdir(parents=True)
    stale = backups / "db-2000-01-01-000000.dump"
    fresh = backups / "db-2099-01-01-000000.dump"
    unrelated = backups / "please-keep-me.txt"
    for f in (stale, fresh, unrelated):
        f.write_bytes(b"x")
    # Only `stale` is backdated past the 1-day retention window.
    subprocess.run(["touch", "-t", "200001010000", str(stale)], check=True)

    assert _run_backup(deploy, bindir).returncode == 0
    assert not stale.exists(), "a stale artifact should have been pruned"
    assert fresh.exists(), "a recent artifact must be kept"
    assert unrelated.exists(), "retention must not touch files this script did not create"
    assert (backups / "MANIFEST.txt").exists(), "the manifest must never be pruned"


def test_backup_never_runs_against_a_stack_that_is_not_up(tmp_path):
    """With no postgres container the script must stop before creating anything."""
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    (bindir / "docker").write_text("#!/bin/sh\nexit 0\n")  # `ps -q postgres` yields nothing
    (bindir / "docker").chmod(0o755)

    proc = _run_backup(deploy, bindir)
    assert proc.returncode != 0
    assert "nothing to back up" in proc.stderr.lower()
    assert not list(backups.glob("db-*")), "no artifact may be created when the stack is down"


def test_systemd_unit_sets_a_restrictive_umask():
    """systemd's default UMask is 0022; the unit must not depend on the script alone."""
    assert re.search(r"^UMask=0?077$", UNIT.read_text(), re.M), "service must set UMask=0077"


# ── the uploads archive must not need a running api container ────────────────────────────────
# The runbook's quiesced procedure stops `api` and `web` before taking the dump/archive pair, so
# anything that reaches the uploads volume via `docker compose exec api` cannot work there:
# `exec` requires a running container. The archive is therefore read by a one-off container.

def test_the_mock_models_a_stopped_api_so_the_next_test_is_not_vacuous(tmp_path):
    """Guard the guard: `exec -T api` against the mock must fail, as it would on a stopped api.

    Without this, a test asserting "backup succeeds while api is stopped" would also pass
    against a mock that happily answered `exec`, proving nothing.
    """
    deploy, _, bindir = _backup_sandbox(tmp_path)
    proc = subprocess.run(
        [str(bindir / "docker"), "compose", "-p", "x", "exec", "-T", "api", "sh", "-c", "tar czf - ."],
        env={"DOCKER_CALL_LOG": str(tmp_path / "probe.log"), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, "the mock must refuse `exec` into a stopped api"
    assert "is not running" in proc.stderr


def test_backup_succeeds_while_the_api_container_is_stopped(tmp_path):
    """The actual regression: this is the quiesced procedure's state (api and web stopped)."""
    deploy, backups, bindir = _backup_sandbox(tmp_path)
    proc = _run_backup(deploy, bindir)
    assert proc.returncode == 0, f"backup must work with api stopped:\n{proc.stdout}\n{proc.stderr}"
    archives = list(backups.glob("uploads-*.tgz"))
    assert len(archives) == 1 and archives[0].stat().st_size > 0


def test_backup_reads_uploads_through_a_one_off_container_not_exec(tmp_path):
    deploy, _, bindir = _backup_sandbox(tmp_path)
    assert _run_backup(deploy, bindir).returncode == 0
    calls = _docker_calls(tmp_path)

    assert not any(" exec -T api" in c for c in calls), \
        f"the uploads archive must not use `exec` into api: {calls}"
    runs = [c for c in calls if " run " in c and c.rstrip().endswith("tar czf - -C /data/uploads .")]
    assert len(runs) == 1, f"expected exactly one one-off uploads reader, got: {calls}"
    assert "/data/uploads" in runs[0]


def test_the_one_off_reader_starts_no_dependency_and_runs_no_migration(tmp_path):
    """--no-deps keeps postgres and the one-shot `migrate` service out of a backup run.

    `--entrypoint sh` matters just as much: the api image's CMD is
    `sh -c "alembic upgrade head && uvicorn ..."`, so without the override a one-off container
    would apply migrations and then try to serve, instead of tarring a volume.
    """
    deploy, _, bindir = _backup_sandbox(tmp_path)
    assert _run_backup(deploy, bindir).returncode == 0
    run = next(c for c in _docker_calls(tmp_path) if " run " in c)

    assert "--no-deps" in run, "a backup must not start linked services"
    assert "--entrypoint sh" in run, "the image CMD runs alembic; it must be overridden"
    assert "--rm" in run, "the throwaway container must be removed"
    assert re.search(r"(^| )-T( |$)", run), "binary stdout needs a disabled pseudo-TTY"
    assert "--pull never" in run, "a backup must not reach a registry"
    assert "--build" not in run, "a backup must never rebuild an image"
    assert "alembic" not in run and "uvicorn" not in run


def test_backup_never_starts_or_restarts_any_service(tmp_path):
    """No `up`, `start` or `restart` anywhere: a backup is a reader, including when quiesced."""
    deploy, _, bindir = _backup_sandbox(tmp_path)
    assert _run_backup(deploy, bindir).returncode == 0
    for call in _docker_calls(tmp_path):
        for verb in (" up ", " up\n", " start ", " restart "):
            assert verb not in f"{call}\n", f"backup must not run `{verb.strip()}`: {call}"


def test_backup_refuses_when_the_api_image_is_absent_rather_than_building_it(tmp_path):
    """Fail closed: a nightly backup must never become an image build on a production host."""
    deploy, backups, bindir = _backup_sandbox(tmp_path, image_present=False)
    proc = _run_backup(deploy, bindir)

    assert proc.returncode != 0
    assert "not present locally" in proc.stderr
    assert not list(backups.glob("uploads-*.tgz")), "no archive may be written"
    assert not (backups / "MANIFEST.txt").exists(), "a failed run must not be recorded as taken"
    assert not any(" run " in c for c in _docker_calls(tmp_path)), \
        "the pre-flight must stop the run before any container is created"
