# G18 — CUSTOMS DATA SCHEMA (dataset packages and storage)

## 1. Storage: `knowledge_datasets` (migration `0011_dataset_provenance`)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `kind` | `HS_RULES` \| `TARIFF` \| `FTA` \| `POLICY` | |
| `version` | string(40) | unique per kind (enforced at import: `409 DUPLICATE_DATASET`) |
| `label` | string(200) | shown in UI; demo labels carry the demo wording |
| `source` | string(300) | legacy free text (kept) |
| `is_demo` | bool | demo fixtures only |
| `effective_from` / `effective_to` | date / date? | effective window |
| `is_active` | bool | operator switch (PATCH, audited) |
| `notes` | text | JSON body (TARIFF/FTA/POLICY payload; `{"rules":[…]}` copy for HS_RULES) |
| `source_authority` | string(200)? | issuing authority |
| `source_document` | string(300)? | legal document number / title |
| `source_reference` | string(500)? | URL / archive reference |
| `ingested_at` | timestamptz? | set at import |
| `verified_at` / `verified_by` | timestamptz? / uuid? | set by `verify` |
| `is_authoritative` | bool, default false | set by `verify` only; `CHECK NOT (is_authoritative AND is_demo)` |
| `checksum` | string(64)? | SHA-256 of canonical payload JSON (`sort_keys`, compact separators, UTF-8) |
| `supersedes_id` | uuid? FK self | lineage |
| `superseded_at` | timestamptz? | set on the OLD dataset by `supersede` |

`hs_rules` rows (`dataset_id`, `heading`, `title`, `keywords`, `exclusions`, `required_attributes`,
`base_confidence`, `notes`) are unchanged and belong to one dataset.

Downgrade: `alembic downgrade 0010_copilot_meta` drops the ten columns and both constraints (tested in the
G18 regression run).

## 2. Import package (JSON) — `POST /api/v1/knowledge/datasets/import` (ADMIN) or `FileImportProvider`

```json
{
  "kind": "TARIFF",
  "version": "mfn-2026-01",
  "label": "Biểu thuế nhập khẩu ưu đãi 2026 (MFN)",
  "effective_from": "2026-01-01",
  "effective_to": null,
  "source_authority": "<issuing authority — owner input>",
  "source_document": "<legal document number/title — owner input>",
  "source_reference": "<URL or archive reference — owner input>",
  "payload": { "rates": { "84131100": { "mfn_duty_pct": 0.0, "vat_pct": 10.0 } } },
  "is_demo": false,
  "notes": "optional free text",
  "reason": "why this package is being imported (audited)"
}
```

A file may hold one object or a list. `is_demo` defaults to false; a demo package can never be verified.

### Payload shapes per kind

| kind | payload | consumed by |
|---|---|---|
| `HS_RULES` | `{"rules": [{"heading","title","keywords":[…],"exclusions":[…],"required_attributes":[…],"base_confidence","notes"}]}` | `app/services/hs_engine.py` |
| `TARIFF` | `{"rates": {"<hs heading or code>": {"mfn_duty_pct": n, "vat_pct": n}}}` | `app/services/valuation.py` |
| `FTA` | `{"forms": {"<FORM>": {"agreement","origin_countries":[…],"allowed_criteria":[…],"preferential_duty_pct":{code: n},"checks":[…]}}}` | `app/services/origin.py` |
| `POLICY` | `{"requirements": {"<heading>": [{"code","title","evidence_doc_types":[…],"needs_reviewer_confirmation","notes"}]}}` | `app/services/policy.py` |

Lookups are by HS heading (4 digits) today; a national 8-digit schedule is loaded with 8-digit keys and the
evaluators will be extended to prefer the longest matching key when the authoritative source is selected (noted
as a follow-up in `G18_OWNER_INPUTS.md`, because the key depth depends on the chosen source).

## 3. Lifecycle API (all audited, all ADMIN/`knowledge.manage`)

| Step | Endpoint | Effect |
|---|---|---|
| import | `POST /knowledge/datasets/import` | stored `is_active=false`, `is_authoritative=false`, checksum computed |
| inspect | `GET /knowledge/datasets/{id}` | includes `provenance_problems` (what blocks verification) |
| verify | `POST /knowledge/datasets/{id}/verify` | `is_authoritative=true`, `verified_at/by`; 409 `MISSING_AUTHORITY` on problems; 403 for non-ADMIN/SENIOR |
| activate | `PATCH /knowledge/datasets/{id}` `{is_active:true}` | becomes a selection candidate |
| supersede | `POST /knowledge/datasets/{id}/supersede` `{new_dataset_id}` | old `superseded_at`, new `supersedes_id` |
| banner | `GET /knowledge/notice` | `app_mode`, `mode_notice`, `demo_active`, `authoritative_datasets`, provider names |

Audit actions: `knowledge.dataset_imported`, `knowledge.dataset_verified`, `knowledge.dataset_superseded`,
`knowledge.dataset_toggled`.
