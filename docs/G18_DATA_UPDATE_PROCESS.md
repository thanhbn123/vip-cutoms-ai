# G18 — CUSTOMS DATA UPDATE PROCESS

Who: **Data steward** (ADMIN) prepares; **Verifier** (ADMIN or SENIOR_REVIEWER, a different person where
possible) verifies; **Reviewers** are informed. Every step is audited and visible in the Knowledge Hub.

## 1. Trigger

- Publication of a new/amended legal document by the selected authority (owner input B-02 names the
  notification channel), or
- a scheduled check (proposed: weekly) of the source for amendments, or
- a reviewer reports a discrepancy (issue code `*_KNOWLEDGE_*` or a manual HS/tax override pattern).

Target: **≤ 5 working days** from publication to verified activation. `vip_customs_dataset_age_days{kind}` on
`/metrics` shows the age of the active dataset; alert when it exceeds the expected cadence
(`G18_MONITORING_ALERTS.md`).

## 2. Prepare the package (steward)

1. Obtain the source file from the licensed channel; keep the original and its hash in the steward's archive.
2. Convert to the package format (`G18_CUSTOMS_DATA_SCHEMA.md`) with the owner-approved adapter. No manual
   editing of rates; if a correction is needed it is a new package with a note.
3. Fill `source_authority`, `source_document`, `source_reference`, `effective_from`, `effective_to`, `version`.
4. `POST /knowledge/datasets/import` with a `reason`. The dataset is INACTIVE and UNVERIFIED.
5. Run the shadow check (staging): activate the package **on staging only**, re-run the pipeline on the
   reference cases, compare assessments with the previous dataset; attach the diff to the change ticket.

## 3. Verify (verifier)

1. Open `GET /knowledge/datasets/{id}`: `provenance_problems` must be empty; checksum shown.
2. Spot-check N records against the legal document (proposed N = 10 random + every changed rate for codes the
   brokerage used in the last 90 days).
3. `POST /knowledge/datasets/{id}/verify` with the reason naming the document checked. Refused on any problem.

## 4. Activate and supersede (steward, during a quiet window)

1. `PATCH /knowledge/datasets/{id}` `{is_active:true}`.
2. `POST /knowledge/datasets/{old}/supersede` `{new_dataset_id}` so the old dataset leaves selection but keeps
   lineage. If both must coexist (non-overlapping effective windows) skip supersession — the selector uses the
   effective date.
3. **Conflict guard:** if two authoritative datasets overlap in time, the evaluators raise
   `*_KNOWLEDGE_CONFLICT` (CRITICAL) and cases block until the steward supersedes one. This is intended.
4. Announce to reviewers (version, effective date, summary of changes). Open cases are **not** recomputed
   automatically; reviewers re-run the pipeline on cases still in progress; released drafts keep their
   recorded `dataset_version`.

## 5. Rollback

Deactivate the new dataset (`PATCH is_active=false`) and clear supersession by importing nothing: the old
dataset is still present; set `superseded_at` back via a corrective supersession only through a ticket (no
direct SQL in production). Document the reason in the audit `reason`.

## 6. Records

Change ticket per package: source file hash, package checksum, verifier, spot-check sheet, staging diff,
activation time. Retained with the legal-source archive (`G18_LEGAL_SOURCE_GOVERNANCE.md`).
