"""G18 — authoritative customs-data governance (B-02 architecture).

Mandatory tests (owner brief §6): expired rule rejected · superseded rule rejected · demo rule rejected in
full mode · missing authority → fail closed · conflicting rules → reviewer required.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.errors import DomainError
from app.db import get_sessionmaker
from app.models.identity import User
from app.models.knowledge import KnowledgeDataset
from app.services import customs_data as cd
from app.services.knowledge import seed_demo

TARIFF_PAYLOAD = {"rates": {"8413": {"mfn_duty_pct": 1.0, "vat_pct": 10.0}}}


def pkg(version="auth-tariff-2026.01", kind="TARIFF", *, effective_from=date(2026, 1, 1), effective_to=None, authority="Test Authority",
        document="Decision 1/2026/TEST", reference="https://example.test/legal/1-2026", payload=None, is_demo=False) -> cd.DatasetPackage:
    return cd.DatasetPackage(kind=kind, version=version, label=f"{kind} {version}", effective_from=effective_from, effective_to=effective_to,
                             source_authority=authority, source_document=document, source_reference=reference,
                             payload=payload or TARIFF_PAYLOAD, is_demo=is_demo)


@pytest.fixture
def db_admin(world):
    db = get_sessionmaker()()
    admin = db.execute(select(User).where(User.id == world.users[("T1", "ADMIN")].id)).scalar_one()
    yield db, admin
    db.close()


def register_verified(db, admin, p: cd.DatasetPackage, active=True) -> KnowledgeDataset:
    ds = cd.register(db, p, admin, reason="t")
    cd.verify(db, ds, admin, reason="t")
    ds.is_active = active
    db.flush()
    return ds


def test_import_is_inactive_unverified_and_checksummed(db_admin):
    db, admin = db_admin
    ds = cd.register(db, pkg(), admin, reason="import")
    assert ds.is_active is False and ds.is_authoritative is False and ds.verified_at is None
    assert ds.checksum == cd.canonical_checksum(TARIFF_PAYLOAD) and ds.ingested_at is not None
    with pytest.raises(DomainError) as e:
        cd.register(db, pkg(), admin, reason="again")
    assert e.value.detail["code"] == "DUPLICATE_DATASET"


def test_missing_authority_fails_closed(db_admin):
    db, admin = db_admin
    ds = cd.register(db, pkg(authority=None), admin, reason="t")
    with pytest.raises(DomainError) as e:
        cd.verify(db, ds, admin, reason="t")
    assert e.value.detail["code"] == "MISSING_AUTHORITY" and "source_authority" in e.value.detail["details"]["problems"]
    assert ds.is_authoritative is False
    ds.is_active = True
    db.flush()
    with pytest.raises(cd.NoActiveDataset):  # unverified → never usable in full mode
        cd.select_dataset(db, "TARIFF", date(2026, 6, 1), mode="full")


def test_demo_dataset_can_never_be_verified_and_is_rejected_in_full_mode(db_admin):
    db, admin = db_admin
    seed_demo(db)
    demo = db.execute(select(KnowledgeDataset).where(KnowledgeDataset.kind == "TARIFF", KnowledgeDataset.is_demo.is_(True))).scalar_one()
    with pytest.raises(DomainError) as e:
        cd.verify(db, demo, admin, reason="t")
    assert "is_demo" in e.value.detail["details"]["problems"]
    assert cd.select_dataset(db, "TARIFF", date.today(), mode="limited").is_demo is True  # limited may use it (labelled)
    with pytest.raises(cd.NoActiveDataset, match="refused in full mode"):
        cd.select_dataset(db, "TARIFF", date.today(), mode="full")


def test_checksum_mismatch_blocks_verification(db_admin):
    db, admin = db_admin
    ds = cd.register(db, pkg(), admin, reason="t")
    ds.notes = '{"rates": {"8413": {"mfn_duty_pct": 0.0, "vat_pct": 10.0}}}'  # tampered body after ingestion
    with pytest.raises(DomainError) as e:
        cd.verify(db, ds, admin, reason="t")
    assert "checksum_mismatch" in e.value.detail["details"]["problems"]


def test_only_admin_or_senior_reviewer_may_verify(db_admin, world):
    db, admin = db_admin
    ds = cd.register(db, pkg(), admin, reason="t")
    reviewer = db.execute(select(User).where(User.id == world.users[("T1", "REVIEWER")].id)).scalar_one()
    with pytest.raises(DomainError) as e:
        cd.verify(db, ds, reviewer, reason="t")
    assert e.value.status_code == 403


def test_expired_rule_rejected(db_admin):
    db, admin = db_admin
    register_verified(db, admin, pkg(effective_from=date(2025, 1, 1), effective_to=date(2025, 12, 31)))
    assert cd.select_dataset(db, "TARIFF", date(2025, 6, 1), mode="full").version == "auth-tariff-2026.01"
    with pytest.raises(cd.NoActiveDataset):
        cd.select_dataset(db, "TARIFF", date(2026, 1, 1), mode="full")


def test_superseded_rule_rejected_and_lineage_kept(db_admin):
    db, admin = db_admin
    old = register_verified(db, admin, pkg("auth-tariff-2026.01"))
    new = register_verified(db, admin, pkg("auth-tariff-2026.07", effective_from=date(2026, 7, 1)))
    cd.supersede(db, old, new, admin, reason="amended by Decision 7/2026")
    assert old.superseded_at is not None and new.supersedes_id == old.id
    assert cd.select_dataset(db, "TARIFF", date(2026, 8, 1), mode="full").version == "auth-tariff-2026.07"
    with pytest.raises(cd.NoActiveDataset):  # the superseded one is never selected, even for dates only it covered
        cd.select_dataset(db, "TARIFF", date(2026, 3, 1), mode="full")
    assert db.get(KnowledgeDataset, old.id) is not None  # lineage preserved, not deleted


def test_conflicting_authoritative_rules_require_reviewer(db_admin):
    db, admin = db_admin
    register_verified(db, admin, pkg("auth-tariff-2026.01"))
    register_verified(db, admin, pkg("auth-tariff-2026.01b"))
    with pytest.raises(cd.ConflictingDatasets, match="reviewer must resolve"):
        cd.select_dataset(db, "TARIFF", date(2026, 3, 1), mode="full")
    with pytest.raises(cd.ConflictingDatasets):  # also in limited mode: the system never silently picks between two legal sources
        cd.select_dataset(db, "TARIFF", date(2026, 3, 1), mode="limited")


def test_authoritative_preferred_over_demo_in_limited_mode(db_admin):
    db, admin = db_admin
    seed_demo(db)
    register_verified(db, admin, pkg(effective_from=date(2026, 1, 1)))
    ds = cd.select_dataset(db, "TARIFF", date.today(), mode="limited")
    assert ds.is_authoritative is True and ds.is_demo is False


def test_conflict_surfaces_as_critical_issue_in_pipeline(db_admin, world, client):
    """End to end: two conflicting authoritative tariff sets → valuation raises TARIFF_KNOWLEDGE_CONFLICT, case BLOCKED."""
    from conftest import FIXTURE_FILES, upload

    db, admin = db_admin
    register_verified(db, admin, pkg("auth-tariff-2026.01"))
    register_verified(db, admin, pkg("auth-tariff-2026.01b"))
    db.commit()
    case = world.create_case()
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        upload(client, world.h(), case["id"], d, FIXTURE_FILES[d])
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    codes = {i["code"] for i in client.get(f"/api/v1/cases/{case['id']}/issues", headers=world.h()).json()}
    assert "TARIFF_KNOWLEDGE_CONFLICT" in codes and r.json()["status"] == "BLOCKED"


def test_api_import_verify_supersede_flow(world, client):
    body = {"kind": "TARIFF", "version": "auth-api-2026.01", "label": "Tariff via API", "effective_from": "2026-01-01",
            "source_authority": "Test Authority", "source_document": "Decision 9/2026/TEST", "source_reference": "https://example.test/9",
            "payload": TARIFF_PAYLOAD, "reason": "owner-supplied package"}
    assert client.post("/api/v1/knowledge/datasets/import", json=body, headers=world.h("REVIEWER")).status_code == 403
    r = client.post("/api/v1/knowledge/datasets/import", json=body, headers=world.h("ADMIN"))
    assert r.status_code == 201, r.text
    ds = r.json()
    assert ds["is_active"] is False and ds["is_authoritative"] is False and ds["checksum"]
    v = client.post(f"/api/v1/knowledge/datasets/{ds['id']}/verify", json={"reason": "checked against gazette"}, headers=world.h("ADMIN"))
    assert v.status_code == 200 and v.json()["is_authoritative"] is True and v.json()["verified_at"]
    # a package without a legal source is refused at verification, with the problems listed
    bad = client.post("/api/v1/knowledge/datasets/import", json=body | {"version": "auth-api-nosrc", "source_document": None},
                      headers=world.h("ADMIN")).json()
    vb = client.post(f"/api/v1/knowledge/datasets/{bad['id']}/verify", json={"reason": "no legal source"}, headers=world.h("ADMIN"))
    assert vb.status_code == 409 and vb.json()["detail"]["code"] == "MISSING_AUTHORITY"
    detail = client.get(f"/api/v1/knowledge/datasets/{bad['id']}", headers=world.h()).json()
    assert "source_document" in detail["provenance_problems"]
    notice = client.get("/api/v1/knowledge/notice", headers=world.h()).json()
    assert notice["authoritative_datasets"] == []  # verified but not yet activated
    client.patch(f"/api/v1/knowledge/datasets/{ds['id']}", json={"is_active": True, "reason": "go live"}, headers=world.h("ADMIN"))
    notice = client.get("/api/v1/knowledge/notice", headers=world.h()).json()
    assert "TARIFF auth-api-2026.01" in notice["authoritative_datasets"]


def test_audit_events_written_for_import_verify_supersede(db_admin):
    from app.models.audit import AuditEvent

    db, admin = db_admin
    old = register_verified(db, admin, pkg("a1"))
    new = register_verified(db, admin, pkg("a2", effective_from=date(2026, 7, 1)))
    cd.supersede(db, old, new, admin, reason="r")
    actions = [e.action for e in db.execute(select(AuditEvent).where(AuditEvent.tenant_id == admin.tenant_id)).scalars()]
    assert actions.count("knowledge.dataset_imported") == 2 and actions.count("knowledge.dataset_verified") == 2
    assert "knowledge.dataset_superseded" in actions
