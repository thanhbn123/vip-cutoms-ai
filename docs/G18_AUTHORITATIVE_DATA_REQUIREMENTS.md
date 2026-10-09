# G18 — AUTHORITATIVE CUSTOMS DATA REQUIREMENTS (B-02 architecture)

Status: **schema, provider interface, verification workflow and fail-closed selection implemented; the
authoritative SOURCE is an OWNER INPUT.** All shipped datasets remain `is_demo=true`, labelled
"DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING". B-02 stays `BLOCKED_OWNER`.

**The system never scrapes the internet and never labels anything authoritative on its own.** A dataset becomes
authoritative only when an ADMIN or SENIOR_REVIEWER verifies it against a named legal source, and the database
refuses `is_authoritative=true` for demo data (`CHECK` constraint, migration `0011_dataset_provenance`).

## 1. Data domains and what "authoritative" must cover

| Domain | Dataset kind | Must include |
|---|---|---|
| HS nomenclature / classification rules | `HS_RULES` | heading-level rules, keywords, exclusions, required attributes, legal note references |
| Import tax rates (MFN / preferential schedules) | `TARIFF` | rate per HS code, rate type, effective window, legal document |
| VAT rules relevant to imports | `TARIFF` (`vat_pct` per code) or a dedicated `TAX` kind in a later migration | VAT rate per code, exemptions, effective window |
| FTA preferential rates | `FTA` (`preferential_duty_pct`) | agreement, form, origin countries, rate per code, effective window |
| C/O rules | `FTA` (`allowed_criteria`, `checks`) | origin criteria per agreement, documentary checks |
| Specialized management policy | `POLICY` | requirement per heading, evidence document types, issuing authority |
| Effective dates | all | `effective_from`, `effective_to` on every dataset |
| Legal-document source reference | all | `source_authority`, `source_document`, `source_reference` |
| Amendment / supersession tracking | all | `supersedes_id`, `superseded_at`; the old dataset is kept for lineage |

## 2. Required fields on every production rule record (owner brief §6)

| Field | Where | Set by |
|---|---|---|
| `source_authority` | `knowledge_datasets.source_authority` | import |
| `source_document` | `knowledge_datasets.source_document` | import |
| `source_url/reference` | `knowledge_datasets.source_reference` | import |
| `effective_from` / `effective_to` | `knowledge_datasets` | import |
| `version` | `knowledge_datasets.version` (unique per kind) | import |
| `ingested_at` | `knowledge_datasets.ingested_at` | import (server time) |
| `verified_at` / `verified_by` | `knowledge_datasets` | verification by ADMIN/SENIOR_REVIEWER |
| `is_authoritative` | `knowledge_datasets.is_authoritative` | verification only |
| `checksum` | `knowledge_datasets.checksum` = SHA-256 of the canonical JSON payload | import; re-checked at verification |

Records inside a dataset (HS rules rows, tariff rates) inherit the dataset's provenance; a row-level legal note
goes in the row's `notes`. Assessments already store `dataset_version` and `dataset_is_demo` per computed value,
so every rule-derived number is traceable to a versioned, checksummed dataset.

## 3. Decision rules (implemented in `apps/api/app/services/customs_data.py`)

- `select_dataset(kind, on, mode)` is the **only** path evaluators use:
  - never a superseded dataset; never one outside its effective window;
  - `full`: only `is_authoritative AND verified_at AND NOT is_demo`; none → `NoActiveDataset`;
  - two usable authoritative datasets on the same date → `ConflictingDatasets` → CRITICAL
    `*_KNOWLEDGE_CONFLICT` issue, reviewer required (in every mode: the system never picks between two legal sources);
  - `demo`/`limited`: authoritative preferred; otherwise the demo dataset (labelled).
- The production decision engine therefore **refuses `is_authoritative=false` for any filing decision**, because
  `APP_MODE=full` is the only mode whose policy sets `real_filing_decisions=true`, and in that mode selection
  rejects unverified/demo data.
- Verification (`verify`) fails closed with `409 MISSING_AUTHORITY` listing the problems: missing
  `source_authority`/`source_document`/`source_reference`/`effective_from`/`version`, `is_demo`, `checksum`
  missing or mismatched. Only ADMIN / SENIOR_REVIEWER may verify (403 otherwise). Every import, verification,
  supersession and activation is audited.

Tests: `apps/api/tests/test_g18_authoritative_data.py` (expired, superseded, demo-in-full, missing authority,
conflict → reviewer, API flow, audit) and `test_g18_modes_readiness.py` (readiness per kind).

## 4. Source requirements the owner's selection must satisfy (B-02 decision brief)

1. **Authority**: the source must be the issuing authority's publication or a licensed redistribution with a
   contractual accuracy commitment. A commercial aggregator is acceptable only with a licence that names the
   underlying legal documents per record.
2. **Completeness**: HS at the national tariff-line depth used in filings; MFN and every FTA schedule the
   brokerage uses; VAT; specialized-management lists; all with effective dates.
3. **Machine-readable delivery**: JSON/CSV/XML with a documented schema, or a feed; mapped into the package
   format of `docs/G18_CUSTOMS_DATA_SCHEMA.md` by an owner-approved adapter (a `CustomsDataProvider`).
4. **Update cadence and notification**: how amendments are announced; target ≤ 5 working days from publication
   to verified activation (`docs/G18_DATA_UPDATE_PROCESS.md`).
5. **Licence**: permits storage, internal redistribution to reviewers and inclusion of references in exported
   drafts.
6. **Verification capacity**: a named ADMIN/SENIOR_REVIEWER accountable for verifying each package.

## 5. What remains demo until then

`apps/api/app/services/demo_fixtures.py` — hand-written illustrative data. It stays, visibly labelled, for demo
and limited modes and for tests. It is never a fallback in full mode.
