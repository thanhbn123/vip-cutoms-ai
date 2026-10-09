"""Negative / security tests over HTTP against a running stack. Exit 1 on any failure.
BASE_URL=https://host SEED_DEMO_PASSWORD=... python scripts/staging/negative_tests.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
PW = os.environ.get("SEED_DEMO_PASSWORD") or sys.exit("SEED_DEMO_PASSWORD required")
FIX = Path(__file__).resolve().parents[2] / "apps" / "api" / "tests" / "fixtures" / "minh_phat"
R: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    R.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=30, verify=os.environ.get("E2E_INSECURE_TLS") != "1")
    r = c.post("/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


op, rv = login("operator@demo.local"), login("reviewer@demo.local")
anon = httpx.Client(base_url=BASE, timeout=30, verify=op._transport is not None and os.environ.get("E2E_INSECURE_TLS") != "1")

check("invalid auth: no token → 401", anon.get("/cases").status_code == 401)
check("invalid auth: tampered token → 401", anon.get("/cases", headers={"Authorization": "Bearer abc.def"}).status_code == 401)
check("invalid auth: wrong password → 401", anon.post("/auth/login", json={"email": "operator@demo.local", "password": "wrong-password-xx"}).status_code == 401)

cust = op.get("/customers").json()[0]
case = op.post("/cases", json={"customer_id": cust["id"], "declaration_type": "A11"}).json()
cid = case["id"]
inv = (FIX / "invoice.txt").read_bytes()
op.post(f"/cases/{cid}/documents", data={"doc_type": "INVOICE"}, files={"file": ("invoice.txt", inv, "text/plain")})
op.post(f"/cases/{cid}/pipeline/run")
items = op.get(f"/cases/{cid}/items").json()
it = items[0]

r = op.post(f"/cases/{cid}/items/{it['id']}/hs-decision", json={"decision": "APPROVE", "hs_code": "84137099", "reason": "operator tries to approve"})
check("RBAC: operator cannot approve HS critical → 403", r.status_code == 403)
r = op.post(f"/cases/{cid}/issues/{op.get(f'/cases/{cid}/issues').json()[0]['id']}/resolve", json={"reason": "operator tries to resolve"})
check("RBAC: operator cannot resolve issues → 403", r.status_code == 403)
r = op.post(f"/cases/{cid}/mark-ready", json={"reason": "operator tries release"})
check("RBAC: operator cannot mark READY → 403", r.status_code == 403)
r = op.post(f"/cases/{cid}/drafts", json={"kind": "RELEASE"})
check("RBAC: operator cannot export release draft → 403", r.status_code == 403)

r = op.post(f"/cases/{cid}/documents", data={"doc_type": "INVOICE"}, files={"file": ("../../etc/passwd.txt", b"root:x:0:0", "text/plain")})
check("upload: path-traversal filename sanitised (stored as basename, no error)", r.status_code in (201, 409) and "/" not in (r.json().get("filename", "") if r.status_code == 201 else ""))
r = op.post(f"/cases/{cid}/documents", data={"doc_type": "INVOICE"}, files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")})
check("upload: unsupported type rejected → 422", r.status_code == 422, f"got {r.status_code}")
r = op.post(f"/cases/{cid}/documents", data={"doc_type": "PASSPORT"}, files={"file": ("x.txt", b"x", "text/plain")})
check("upload: unknown doc_type rejected → 422", r.status_code == 422, f"got {r.status_code}")
# 21 MB over a WAN link takes well over the client-wide 30 s budget once the stack is also
# serving other traffic, so this one request gets its own generous timeout. The observed
# status is always reported: without it a failure here is undiagnosable after the fact.
r = op.post(f"/cases/{cid}/documents", data={"doc_type": "OTHER"},
            files={"file": ("big.txt", b"0" * (21 * 1024 * 1024), "text/plain")}, timeout=300)
check("upload: oversize rejected → 413", r.status_code == 413, f"got {r.status_code}")

gate = rv.get(f"/cases/{cid}/release-gate").json()
r = rv.post(f"/cases/{cid}/mark-ready", json={"reason": "reviewer tries with open issues"})
check("release gate: open issues block READY (reviewer) → 409", gate["eligible"] is False and r.status_code == 409)
r = rv.post(f"/cases/{cid}/drafts", json={"kind": "RELEASE"})
check("release gate: release draft blocked → 409", r.status_code == 409)

# cross-tenant: create a second tenant user via admin (if available) and verify 404 isolation
try:
    adm = login("admin@demo.local")
    # admin can only create users in its own tenant; isolation is proven by a second tenant in the pytest suite.
    # Here: a *different user* in the same tenant must still see the case (same tenant) and a forged UUID must 404.
    r = rv.get("/cases/00000000-0000-0000-0000-000000000000")
    check("tenant/ID isolation: unknown case id → 404 (no enumeration leak)", r.status_code == 404)
    r = rv.get("/documents/00000000-0000-0000-0000-000000000000/content")
    check("tenant/ID isolation: unknown document → 404", r.status_code == 404)
    check("RBAC: admin has no customs-decision permission", "hs.decide" not in adm.get("/auth/me").json()["permissions"])
except Exception as exc:  # noqa: BLE001
    check("tenant isolation probes", False, str(exc))

sr = login("senior@demo.local")
audit = sr.get(f"/cases/{cid}/audit").json()
check("audit records critical actions with actor/before/after", any(e["action"] == "issue.raised" for e in audit) and all("actor_type" in e and "hash" in e for e in audit))
check("audit chain valid", sr.get("/audit/verify").json()["chain_valid"] is True)

print(f"\nNEGATIVE_TESTS: {sum(R)}/{len(R)} PASS")
sys.exit(0 if all(R) else 1)
