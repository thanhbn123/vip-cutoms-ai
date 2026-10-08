# Product Specification

## Vision

VIP Customs AI is a customs operations system, not a generic chatbot. It converts trade documents into structured, reviewable declaration data while keeping humans in control of high-impact decisions.

## Primary users

- Operator: prepares cases and documents.
- Reviewer: validates HS, C/O, valuation, policy and critical discrepancies.
- Senior Reviewer: handles high-risk or exceptional cases.
- Admin: manages users, tenants, knowledge sources and system configuration.

## Core objects

- Customer / Importer
- Supplier / Exporter
- Customs Case / Shipment
- Document
- Extracted Field + Source Lineage
- Goods Item
- HS Candidate / Classification Decision
- Tariff Result
- C/O / FTA Assessment
- Policy Assessment
- Reviewer Decision
- Declaration Draft + Version
- Audit Event
- Approved Product Memory

## Core workflow

1. Create case.
2. Upload documents.
3. Parse/OCR.
4. Map fields with confidence and provenance.
5. Normalize line items.
6. Run HS candidate analysis.
7. Run valuation/tax/C/O/policy checks.
8. Detect discrepancies.
9. AI Copilot explains and proposes actions.
10. Reviewer resolves critical issues.
11. Create versioned declaration draft.
12. Audit every decision.
13. Approved outcomes become reusable enterprise memory.

## MVP scope

MVP should demonstrate one complete import case using Invoice + Packing List and optional B/L/Form E fixtures.

MVP must not claim legal correctness from demo rules or submit a declaration to production customs systems.

## UX requirements

The implemented UI should preserve the V12 concepts:

- case readiness score,
- document status,
- field-level source/confidence,
- goods table,
- HS candidate and reasoning summary,
- open issues,
- AI Copilot,
- reviewer queue,
- release gate,
- historical learning references.
