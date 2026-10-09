# G18 — LEGAL SOURCE GOVERNANCE

Purpose: make every rule-derived value in a draft traceable to a named legal document, a version, a checksum
and a verifier — and make it impossible for unverified or demo data to drive a real filing decision.

## 1. Principles

1. **One source of authority per domain**, selected by the owner (B-02) and recorded in `G18_OWNER_INPUTS.md`.
   Secondary sources may inform the steward but are never imported as authoritative.
2. **Provenance is mandatory**: `source_authority`, `source_document`, `source_reference`, effective window,
   version, checksum. Verification refuses otherwise (`409 MISSING_AUTHORITY`).
3. **Separation of duties**: the steward who imports is not the verifier where staffing allows; both actions
   are audited with user identity and reason.
4. **Demo data is quarantined by the database**: `CHECK NOT (is_authoritative AND is_demo)`.
5. **Supersession, never deletion**: amended datasets stay for lineage; released drafts cite the
   `dataset_version` that was in force.
6. **Conflicts stop the line**: overlapping authoritative datasets block affected cases until resolved by a
   human; the software never chooses between two legal sources.
7. **No scraping**: ingestion is from the licensed channel through an explicit `CustomsDataProvider`
   (`FileImportProvider` today). No code path fetches tariff data from the public internet.
8. **Mode gate**: only `APP_MODE=full` may treat values as filing-grade, and only with verified authoritative
   datasets for all four kinds; `/ready` enforces it.

## 2. Roles

| Role | May |
|---|---|
| ADMIN (`knowledge.manage`) | import, activate/deactivate, supersede, verify |
| SENIOR_REVIEWER | verify (via service rule `VERIFIER_ROLES`); API exposure of verify to this role follows when the permission matrix is extended — today the endpoint requires `knowledge.manage` |
| REVIEWER / OPERATOR | read datasets, see provenance and banners |

## 3. Records to keep (outside the application)

- Legal-source archive: original documents/files with hashes, licence, correspondence with the authority/vendor.
- Change tickets per package (see `G18_DATA_UPDATE_PROCESS.md`).
- Quarterly review: list active authoritative datasets, their ages, verifiers; confirm licence validity.

## 4. Liability note (for the owner)

Until B-02 is resolved, every tariff/FTA/policy value is demo and the product is correctly refusing full mode.
After B-02, correctness of a filing still depends on reviewer approval (product rule #2); the governance above
makes the data trail auditable, it does not make the software the declarant.
