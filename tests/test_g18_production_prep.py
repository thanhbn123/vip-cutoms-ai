"""G18 full-production preparation — infrastructure contract tests (no database, no Docker, no network).

Covers:
  * scripts/production/backup_offsite.sh — refuses without an owner-configured destination, refuses plaintext
    off-host by default, verifies checksums before replicating, uploads via a mocked rclone, applies GFS
    prefixes, writes the status JSON the API reads for /ready, never prints the env file.
  * the off-site systemd units reference real files and the local backup unit.
  * env templates and compose files carry the G18 mode/provider/backup settings with safe defaults.
  * scripts/staging/deactivate_demo_users.sh (B-07 wrapper) is executable, valid and requires confirmation.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
OFFSITE = REPO / "scripts" / "production" / "backup_offsite.sh"
DEACTIVATE_SH = REPO / "scripts" / "staging" / "deactivate_demo_users.sh"
DEACTIVATE_PY = REPO / "apps" / "api" / "scripts" / "deactivate_demo_users.py"
PROD_ENV = REPO / "infra" / "production" / ".env.production.example"
ROOT_ENV = REPO / ".env.example"
STAGING_COMPOSE = REPO / "infra" / "staging" / "docker-compose.staging.yml"
PROD_OVERLAY = REPO / "infra" / "production" / "docker-compose.production.yml"
UNIT = REPO / "infra" / "production" / "vip-customs-backup-offsite.service"
TIMER = REPO / "infra" / "production" / "vip-customs-backup-offsite.timer"


def _env(path: pathlib.Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#", 1)[0].strip()
    return out


# ---------------------------------------------------------------------------- static contracts
def test_offsite_script_is_executable_and_valid():
    assert OFFSITE.stat().st_mode & stat.S_IXUSR
    subprocess.run(["bash", "-n", str(OFFSITE)], check=True)


def test_offsite_script_carries_no_credential_and_names_owner_input():
    text = OFFSITE.read_text()
    assert "OWNER INPUT" in text
    assert not re.search(r"(AKIA[0-9A-Z]{16}|age1[0-9a-z]{50,}|-----BEGIN)", text)
    assert "umask 077" in text


def test_offsite_units_reference_existing_script_and_local_backup_unit():
    unit, timer = UNIT.read_text(), TIMER.read_text()
    m = re.search(r"^ExecStart=.*?bash\s+(\S+)", unit, re.M)
    assert m and (REPO / m.group(1)).is_file()
    assert "After=vip-customs-backup.service" in unit and "Type=oneshot" in unit and "UMask=0077" in unit
    assert "Unit=vip-customs-backup-offsite.service" in timer and "Persistent=true" in timer


@pytest.mark.parametrize("key", ["APP_MODE", "AI_PROVIDER", "DOCUMENT_OCR_PROVIDER", "DOCUMENT_AI_PROVIDER", "HS_AI_PROVIDER",
                                 "COPILOT_PROVIDER", "AI_PROVIDER_BASE_URL", "AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL", "AI_DAILY_BUDGET_USD",
                                 "OFFSITE_METHOD", "OFFSITE_TARGET", "OFFSITE_ENCRYPT_RECIPIENT", "OFFSITE_RETENTION_DAILY",
                                 "OFFSITE_RETENTION_WEEKLY", "OFFSITE_RETENTION_MONTHLY", "BACKUP_STATUS_FILE"])
def test_production_template_documents_g18_keys(key):
    assert key in _env(PROD_ENV)


def test_production_template_defaults_are_safe():
    env = _env(PROD_ENV)
    assert env["APP_MODE"] == "limited", "a production host runs limited until B-01/B-02 are resolved"
    assert env["AI_PROVIDER"] == "mock"
    for k in ("AI_PROVIDER_API_KEY", "AI_PROVIDER_BASE_URL", "OFFSITE_TARGET", "OFFSITE_ENCRYPT_RECIPIENT"):
        assert env[k] == "", f"{k} must be an empty placeholder"
    assert (env["OFFSITE_RETENTION_DAILY"], env["OFFSITE_RETENTION_WEEKLY"], env["OFFSITE_RETENTION_MONTHLY"]) == ("7", "4", "6")
    assert "PROPOSED_OWNER_APPROVAL_REQUIRED" in PROD_ENV.read_text()


def test_root_env_example_defaults_to_demo_mode_and_mock():
    env = _env(ROOT_ENV)
    assert env["APP_MODE"] == "demo" and env["AI_PROVIDER"] == "mock" and env["AI_PROVIDER_API_KEY"] == ""


def test_compose_passes_mode_and_provider_settings_with_safe_defaults():
    text = STAGING_COMPOSE.read_text()
    assert "APP_MODE: ${APP_MODE:-limited}" in text
    assert "RELEASE_SHA: ${IMAGE_TAG:-}" in text
    for k in ("DOCUMENT_OCR_PROVIDER", "DOCUMENT_AI_PROVIDER", "HS_AI_PROVIDER", "COPILOT_PROVIDER", "AI_PROVIDER_API_KEY", "BACKUP_STATUS_FILE"):
        assert f"{k}: ${{{k}:-}}" in text, k


def test_production_overlay_mounts_backup_dir_read_only():
    text = PROD_OVERLAY.read_text()
    assert re.search(r"\$\{BACKUP_DIR:-/var/backups/vip-customs\}:/data/backups:ro", text)
    assert "uploads:/data/uploads" in text, "overriding `volumes` must keep the uploads volume"
    assert _env(PROD_ENV)["BACKUP_STATUS_FILE"] == "/data/backups/backup-status.json"


# ---------------------------------------------------------------------------- B-07 wrapper
def test_deactivate_wrapper_is_executable_valid_and_requires_confirmation():
    assert DEACTIVATE_SH.stat().st_mode & stat.S_IXUSR
    subprocess.run(["bash", "-n", str(DEACTIVATE_SH)], check=True)
    text = DEACTIVATE_SH.read_text()
    assert 'DEACTIVATE_CONFIRM" = "demo.local"' in text and "--execute" in text and "exec -T api python scripts/deactivate_demo_users.py" in text
    assert DEACTIVATE_PY.is_file()
    py = DEACTIVATE_PY.read_text()
    assert "is_active = False" in py and "db.delete" not in py, "B-07 deactivates; it never deletes identity rows"

def test_deactivate_script_targets_only_demo_local_addresses():
    py = DEACTIVATE_PY.read_text()
    assert r"@demo\.local$" in py and "CONFIRM_TOKEN" in py and "user.deactivated" in py


# ---------------------------------------------------------------------------- execution tests (mocked rclone / age)
def _write_env(tmp_path: pathlib.Path, backup_dir: pathlib.Path, **kv) -> pathlib.Path:
    env = tmp_path / "prod.env"
    lines = [f"BACKUP_DIR={backup_dir}", "POSTGRES_PASSWORD=super-secret-db-password-not-for-logs", "APP_SECRET_KEY=another-secret-value"]
    lines += [f"{k}={v}" for k, v in kv.items()]
    env.write_text("\n".join(lines) + "\n")
    return env


def _local_backup(backup_dir: pathlib.Path, *, corrupt=False) -> None:
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    for name, data in (("db-20260101-0230.dump", b"PGDMP-fake\n"), ("uploads-20260101-0230.tgz", b"\x1f\x8b-fake\n")):
        (backup_dir / name).write_bytes(data)
        digest = hashlib.sha256(b"tampered" if corrupt else data).hexdigest()
        (backup_dir / f"{name}.sha256").write_text(f"{digest}  {name}\n")
    (backup_dir / "MANIFEST.txt").write_text("stamp fake\n")


def _fake_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "rclone.log"
    (bin_dir / "rclone").write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log}"
case "$1" in
  copy)  dest="${{@: -1}}"; src="${{@: -2:1}}"; mkdir -p "{tmp_path}/remote/${{dest#remote:bucket/}}"; cp -r "$src"/. "{tmp_path}/remote/${{dest#remote:bucket/}}/" ;;
  lsf)   ls -1 "{tmp_path}/remote/${{3#remote:bucket/}}" 2>/dev/null | sed 's#$#/#' ;;
  purge) rm -rf "{tmp_path}/remote/${{2#remote:bucket/}}" ;;
esac
""")
    (bin_dir / "age").write_text("#!/usr/bin/env bash\n# fake age: -r KEY -o OUT IN\nprintf 'AGE-ENCRYPTED:' > \"$4\"; cat \"$5\" >> \"$4\"\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    return bin_dir


def _run(tmp_path, env_file, extra_path=None):
    env = dict(os.environ, DEPLOY_PATH=str(tmp_path), ENV_FILE=str(env_file), TMPDIR=str(tmp_path))
    if extra_path:
        env["PATH"] = f"{extra_path}:{env['PATH']}"
    return subprocess.run(["bash", str(OFFSITE)], capture_output=True, text=True, env=env, timeout=60)


def test_offsite_refuses_without_destination(tmp_path):
    bd = tmp_path / "backups"
    _local_backup(bd)
    r = _run(tmp_path, _write_env(tmp_path, bd))
    assert r.returncode == 3 and "OWNER INPUT" in r.stderr
    assert not (bd / "backup-status.json").exists()


def test_offsite_refuses_plaintext_by_default(tmp_path):
    bd = tmp_path / "backups"
    _local_backup(bd)
    r = _run(tmp_path, _write_env(tmp_path, bd, OFFSITE_METHOD="rclone", OFFSITE_TARGET="remote:bucket/vip"), _fake_bin(tmp_path))
    assert r.returncode == 4 and "PLAINTEXT" in r.stderr


def test_offsite_refuses_corrupt_local_artifact(tmp_path):
    bd = tmp_path / "backups"
    _local_backup(bd, corrupt=True)
    r = _run(tmp_path, _write_env(tmp_path, bd, OFFSITE_METHOD="rclone", OFFSITE_TARGET="remote:bucket/vip",
                                  OFFSITE_ENCRYPT_RECIPIENT="age1fakerecipientkey"), _fake_bin(tmp_path))
    assert r.returncode == 1 and "checksum mismatch" in r.stderr and not (tmp_path / "remote").exists()


def test_offsite_encrypts_uploads_prunes_and_writes_status(tmp_path):
    bd = tmp_path / "backups"
    _local_backup(bd)
    env = _write_env(tmp_path, bd, OFFSITE_METHOD="rclone", OFFSITE_TARGET="remote:bucket/vip", OFFSITE_ENCRYPT_RECIPIENT="age1fakerecipientkey",
                     OFFSITE_RETENTION_DAILY="1", BACKUP_STATUS_FILE=str(tmp_path / "status.json"))
    r1 = _run(tmp_path, env, _fake_bin(tmp_path))
    assert r1.returncode == 0, r1.stderr
    daily = tmp_path / "remote" / "vip" / "daily"
    runs = sorted(p for p in daily.iterdir())
    assert len(runs) == 1
    names = {p.name for p in runs[0].iterdir()}
    assert "db-20260101-0230.dump.age" in names and "uploads-20260101-0230.tgz.age" in names and "MANIFEST.txt" in names
    assert "db-20260101-0230.dump" not in names, "plaintext dump must not leave the host when a recipient is configured"
    assert (runs[0] / "db-20260101-0230.dump.age").read_bytes().startswith(b"AGE-ENCRYPTED:")
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["offsite"] is True and status["encrypted"] is True and status["destination_kind"] == "rclone"
    assert status["last_success_at"].endswith("Z") and any(p.startswith("daily/") for p in status["prefixes"])
    assert stat.S_IMODE((tmp_path / "status.json").stat().st_mode) == 0o600
    # the env file's secrets never appear in output
    for secret in ("super-secret-db-password-not-for-logs", "another-secret-value"):
        assert secret not in r1.stdout + r1.stderr
    # second run → retention 1 keeps only the newest daily copy
    r2 = _run(tmp_path, env, _fake_bin(tmp_path))
    assert r2.returncode == 0, r2.stderr
    assert len(list(daily.iterdir())) == 1


def test_offsite_fails_when_no_local_backup_exists(tmp_path):
    bd = tmp_path / "backups"
    bd.mkdir(mode=0o700)
    r = _run(tmp_path, _write_env(tmp_path, bd, OFFSITE_METHOD="rclone", OFFSITE_TARGET="remote:bucket/vip", OFFSITE_ALLOW_PLAINTEXT="yes"),
             _fake_bin(tmp_path))
    assert r.returncode == 1 and "no local backup pair" in r.stderr
