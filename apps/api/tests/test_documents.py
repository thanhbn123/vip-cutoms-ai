from conftest import upload


def test_upload_sets_metadata_storage_status_and_audit(world, client):
    case = world.create_case()
    r = upload(client, world.h(), case["id"], "INVOICE", "invoice.txt")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["version"] == 1 and doc["is_current"] and doc["status"] == "UPLOADED"
    assert len(doc["sha256"]) == 64 and doc["size_bytes"] > 0
    assert "storage_key" not in doc  # no storage paths/URLs exposed
    assert client.get(f"/api/v1/cases/{case['id']}", headers=world.h()).json()["status"] == "DOCUMENTS_UPLOADED"
    actions = [e["action"] for e in client.get(f"/api/v1/cases/{case['id']}/audit", headers=world.h()).json()]
    assert "document.uploaded" in actions and "case.status_changed" in actions
    content = client.get(f"/api/v1/documents/{doc['id']}/content", headers=world.h())
    assert content.status_code == 200 and b"INV-2026-889" in content.content


def test_reupload_creates_new_version_and_supersedes(world, client):
    case = world.create_case()
    v1 = upload(client, world.h(), case["id"], "INVOICE", "invoice.txt").json()
    v2 = upload(client, world.h(), case["id"], "INVOICE", "invoice.txt", content=b"Invoice No: INV-2026-889-R1\n").json()
    assert v2["version"] == 2 and v2["supersedes_id"] == v1["id"]
    current = client.get(f"/api/v1/cases/{case['id']}/documents", headers=world.h()).json()
    assert [d["id"] for d in current] == [v2["id"]]
    every = client.get(f"/api/v1/cases/{case['id']}/documents?include_superseded=true", headers=world.h()).json()
    assert {d["status"] for d in every} == {"SUPERSEDED", "UPLOADED"}


def test_duplicate_upload_rejected(world, client):
    case = world.create_case()
    assert upload(client, world.h(), case["id"], "INVOICE", "invoice.txt").status_code == 201
    r = upload(client, world.h(), case["id"], "INVOICE", "invoice.txt")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DUPLICATE_DOCUMENT"


def test_upload_validation(world, client):
    case = world.create_case()
    assert upload(client, world.h(), case["id"], "PASSPORT", "invoice.txt").status_code == 422
    assert upload(client, world.h(), case["id"], "INVOICE", "evil.exe", content=b"MZ").status_code == 422
    assert upload(client, world.h(), case["id"], "INVOICE", "empty.txt", content=b"").status_code == 422


def test_document_access_is_tenant_isolated_and_rbac(world, client):
    case = world.create_case()
    doc = upload(client, world.h(), case["id"], "INVOICE", "invoice.txt").json()
    assert client.get(f"/api/v1/documents/{doc['id']}/content", headers=world.h("OPERATOR", "T2")).status_code == 404
    assert upload(client, world.h("OPERATOR", "T2"), case["id"], "INVOICE", "invoice.txt").status_code == 404
    assert upload(client, world.h("ADMIN"), case["id"], "PACKING_LIST", "packing_list.txt").status_code == 403
