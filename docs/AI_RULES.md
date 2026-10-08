# AI Rules and Safety Contract

## Classification states

- `AUTO_ACCEPTABLE`: non-critical field, high-confidence, deterministic evidence.
- `NEEDS_REVIEW`: evidence exists but ambiguity remains.
- `BLOCKED`: critical evidence missing/conflicting or a required policy decision is unresolved.
- `APPROVED`: reviewer explicitly approved.
- `REJECTED`: reviewer rejected the proposal.

## Confidence is not authority

A high model confidence score does not override missing documentary or technical evidence.

## Critical fields

At minimum treat these as controlled:

- HS classification final decision
- customs valuation adjustments
- C/O/FTA eligibility decision
- specialized-management/policy decision
- declaration type when ambiguous
- data whose conflict can materially change tax/compliance

## Provenance

For each AI-produced field store:

- source document(s)
- source location/page/region when available
- extraction method
- proposed value
- confidence
- model/provider/version metadata when applicable
- timestamp
- reviewer state

## Historical learning

Only reviewer-approved final outcomes can become reusable memory. Rejected, blocked, draft, or purely inferred values must not become authoritative memory.

## Prompt/provider separation

Business rules and validation must be implementable/testable without an LLM. LLM output is untrusted structured input until validated.
