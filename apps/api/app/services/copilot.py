"""Case-scoped Copilot: builds an authorised context, calls the provider, VALIDATES the answer, persists it.

Guardrails: context is built only from this tenant's case; sources returned by the provider must reference ids present in
the context (fabricated references are dropped and flagged); proposals are stored as PROPOSED and never applied here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import get_provider
from app.models.assessment import Assessment
from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.copilot import CopilotMessage, Proposal
from app.models.document import Document
from app.models.extraction import CaseField
from app.models.goods import GoodsItem, HsCandidate
from app.models.identity import User
from app.models.issue import Issue
from app.services import audit, declaration
from app.services.memory import history_for_item


def build_context(db: Session, case: CustomsCase) -> tuple[dict, set[str]]:
    allowed: set[str] = set()
    fields = []
    for f in db.execute(select(CaseField).where(CaseField.case_id == case.id)).scalars():
        fields.append({"key": f.key, "label": f.label, "value": f.value, "confidence": f.confidence, "is_critical": f.is_critical,
                       "review_status": f.review_status, "source_ref": f.source_ref, "document_id": str(f.source_document_id) if f.source_document_id else None})
        allowed.add(str(f.id))
    docs = []
    co_doc = None
    for d in db.execute(select(Document).where(Document.case_id == case.id, Document.is_current.is_(True))).scalars():
        row = {"id": str(d.id), "doc_type": d.doc_type, "version": d.version, "status": d.status, "parse_confidence": d.parse_confidence or 0.0}
        docs.append(row)
        allowed.add(str(d.id))
        if d.doc_type == "CO":
            co_doc = row
    assess = {(a.item_id, a.kind): a for a in db.execute(select(Assessment).where(Assessment.case_id == case.id)).scalars()}
    items = []
    for it in db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id).order_by(GoodsItem.line_no)).scalars():
        cands = []
        for c in db.execute(select(HsCandidate).where(HsCandidate.item_id == it.id, HsCandidate.status != "SUPERSEDED").order_by(HsCandidate.rank)).scalars():
            cands.append({"id": str(c.id), "heading": c.heading, "title": c.title, "confidence": c.confidence, "reasoning": c.reasoning,
                          "missing_attributes": c.missing_attributes, "dataset_version": c.dataset_version})
            allowed.add(str(c.id))
        co = assess.get((it.id, "CO"))
        tax = assess.get((it.id, "TAX"))
        history = history_for_item(db, case, it)
        for h in history:
            allowed.add(h["memory_id"])
        items.append({"id": str(it.id), "line_no": it.line_no, "description": it.description, "description_vn": it.description_vn, "model": it.model,
                      "quantity": it.quantity, "unit_price": it.unit_price, "attributes": it.attributes or {},
                      "source_document_id": str(it.source_document_id) if it.source_document_id else None, "source_ref": it.source_ref,
                      "hs": {"status": it.hs_status, "code": it.hs_code, "confidence": it.hs_confidence, "candidates": cands},
                      "origin": {"status": co.status, "preferential_duty_pct": co.result.get("preferential_duty_pct"), "reviewer_decision": co.reviewer_decision} if co else None,
                      "tax": {"status": tax.status, "result": tax.result} if tax else None, "history": history})
        allowed.add(str(it.id))
    issues = []
    for i in db.execute(select(Issue).where(Issue.case_id == case.id, Issue.status == "OPEN")).scalars():
        issues.append({"id": str(i.id), "code": i.code, "severity": i.severity, "category": i.category, "title": i.title, "detail": i.detail, "target_ref": i.target_ref})
        allowed.add(str(i.id))
    val = assess.get((None, "VALUATION"))
    decl = declaration.build(db, case)
    ctx = {"case": {"id": str(case.id), "case_no": case.case_no, "status": case.status, "declaration_type": case.declaration_type},
           "fields": fields, "documents": docs, "co_document": co_doc, "items": items, "issues": issues,
           "valuation": {"status": val.status, "reasoning": val.reasoning, "result": val.result} if val else None, "readiness": decl["readiness"]}
    return ctx, allowed


def ask(db: Session, case: CustomsCase, user: User, question: str) -> dict:
    ctx, allowed = build_context(db, case)
    provider = get_provider()
    ans = provider.answer_case_question(question, ctx)
    # ---- validate untrusted provider output
    if not ans.answer or not ans.answer.strip():
        raise ValueError("provider returned an empty answer")
    valid_sources, dropped = [], []
    for s in ans.sources:
        if isinstance(s, dict) and str(s.get("id")) in allowed:
            valid_sources.append(s)
        else:
            dropped.append(s)
    reasoning = list(ans.reasoning)
    if dropped:
        reasoning.append(f"[validation] {len(dropped)} nguồn không tồn tại trong hồ sơ đã bị loại.")
    proposal = None
    if ans.proposal:
        p = ans.proposal
        item = db.execute(select(GoodsItem).where(GoodsItem.id == uuid.UUID(str(p["target_ref"])), GoodsItem.case_id == case.id)).scalar()
        if item is not None and p.get("target_type") == "ITEM_DESCRIPTION_VN" and p.get("proposed_value"):
            proposal = Proposal(tenant_id=case.tenant_id, case_id=case.id, target_type="ITEM_DESCRIPTION_VN", target_ref=str(item.id),
                                current_value=item.description_vn, proposed_value=str(p["proposed_value"])[:2000], reasoning=reasoning,
                                sources=valid_sources, provider=provider.name, status="PROPOSED", requested_by=user.id, created_at=utcnow())
            db.add(proposal)
            db.flush()
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.ai(), action="proposal.created", entity_type="proposal", entity_id=proposal.id,
                         case_id=case.id, before={"value": item.description_vn}, after={"proposed_value": proposal.proposed_value, "target": str(item.id)},
                         reason=f"Copilot DESCRIBE requested by {user.email}", evidence=valid_sources)
    confidence = round(max(0.0, min(1.0, float(ans.confidence or 0.0))), 2)
    if dropped:
        confidence = round(confidence * 0.5, 2)  # fabricated references halve our trust in the answer
    actions = [str(a)[:300] for a in (ans.recommended_actions or [])][:10]
    requires_review = bool(ans.requires_review) or proposal is not None or any(i["severity"] == "CRITICAL" for i in ctx["issues"])
    meta = {"confidence": confidence, "recommended_actions": actions, "requires_review": requires_review, "dropped_sources": len(dropped)}
    now = utcnow()
    db.add(CopilotMessage(tenant_id=case.tenant_id, case_id=case.id, user_id=user.id, role="USER", content=question, meta={}, created_at=now))
    ai_msg = CopilotMessage(tenant_id=case.tenant_id, case_id=case.id, user_id=user.id, role="AI", content=ans.answer, intent=ans.intent,
                            sources=valid_sources, reasoning=reasoning, provider=provider.name, provider_version=provider.version,
                            proposal_id=proposal.id if proposal else None, meta=meta, created_at=now)
    db.add(ai_msg)
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.ai(), action="copilot.answered", entity_type="copilot_message", entity_id=ai_msg.id,
                 case_id=case.id, after={"intent": ans.intent, "sources": len(valid_sources), "dropped_sources": len(dropped), "proposal": bool(proposal)},
                 reason=question[:500])
    return {"answer": ans.answer, "intent": ans.intent, "sources": valid_sources, "reasoning": reasoning, "provider": provider.name,
            "provider_version": provider.version, "proposal_id": str(proposal.id) if proposal else None, "message_id": str(ai_msg.id),
            "confidence": confidence, "recommended_actions": actions, "requires_review": requires_review}
