"""Valuation + tax primitives (deterministic). Demo tariff → illustrative amounts, flagged as non-authoritative."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.models.extraction import CaseField
from app.models.goods import GoodsItem
from app.services import assessments, audit
from app.services.hs_lookup import lookup
from app.services.issues import IssueSpec, sync
from app.services.knowledge import ConflictingDatasets, NoActiveDataset, dataset_payload, require_dataset
from app.services.normalize import norm_text, parse_decimal

Q = Decimal("0.01")


def _fields(db: Session, case: CustomsCase) -> dict[str, CaseField]:
    return {f.key: f for f in db.execute(select(CaseField).where(CaseField.case_id == case.id)).scalars()}


def _usable(f: CaseField | None) -> Decimal | None:
    """A value is usable for calculation when present and not REJECTED/BLOCKED."""
    if f is None or not f.value or f.review_status in ("REJECTED", "BLOCKED"):
        return None
    return parse_decimal(f.value)


def evaluate(db: Session, case: CustomsCase, actor: audit.Actor) -> None:
    fields = _fields(db, case)
    items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id).order_by(GoodsItem.line_no)).scalars().all()
    specs: list[IssueSpec] = []
    inc = norm_text(fields["valuation.incoterm"].value) if fields.get("valuation.incoterm") and fields["valuation.incoterm"].value else ""
    total = _usable(fields.get("invoice.total_amount"))
    freight = _usable(fields.get("valuation.freight"))
    insurance = _usable(fields.get("valuation.insurance"))
    currency = fields["valuation.currency"].value if fields.get("valuation.currency") else None
    line_sum = sum((parse_decimal(i.amount) or Decimal(0)) for i in items) if items else None
    reasoning = []
    if total is not None and line_sum is not None and items and abs(total - line_sum) > Decimal("0.01"):
        specs.append(IssueSpec("invoice_total", "INVOICE_TOTAL_MISMATCH", "WARNING", "VALUATION",
                               f"Tổng Invoice {total} ≠ tổng dòng hàng {line_sum}", "Trị giá dùng tổng Invoice đã khai; reviewer phải xác nhận trước khi phát hành.",
                               target_ref="invoice.total_amount", auto_resolvable=True))
        reasoning.append(f"Tổng hóa đơn {total} khác tổng dòng {line_sum}; dùng tổng hóa đơn đã khai, reviewer phải xử lý cảnh báo.")
    basis = total if total is not None else line_sum  # declared invoice total is the valuation basis (D-007)
    additions = Decimal(0)
    status = "COMPUTED"
    if inc.startswith(("FOB", "EXW", "FCA", "CFR", "CPT")):
        if inc.startswith(("FOB", "EXW", "FCA")):
            if freight is None:
                status = "INPUT_MISSING"
                reasoning.append("Thiếu cước vận tải (khoản cộng) → chưa tính được trị giá tính thuế.")
            else:
                additions += freight
        if insurance is None:
            status = "INPUT_MISSING"
            reasoning.append("Thiếu phí bảo hiểm (khoản cộng) → chưa tính được trị giá tính thuế.")
        else:
            additions += insurance
    elif not inc:
        status = "INPUT_MISSING"
        reasoning.append("Chưa có Incoterm.")
    customs_value = (basis + additions).quantize(Q) if basis is not None and status == "COMPUTED" else None
    reasoning.insert(0, f"Incoterm {inc or '?'}: trị giá = giá hóa đơn {basis} + khoản cộng {additions}.")
    assessments.upsert(db, case, "VALUATION", None, status=status, ds=None,
                       inputs={"incoterm": inc, "invoice_total": str(total) if total is not None else None, "line_sum": str(line_sum) if line_sum is not None else None,
                               "freight": str(freight) if freight is not None else None, "insurance": str(insurance) if insurance is not None else None,
                               "currency": currency},
                       result={"customs_value": str(customs_value) if customs_value is not None else None, "currency": currency,
                               "note": "Deterministic arithmetic over mapped fields; reviewer must approve critical inputs."},
                       reasoning=reasoning)

    # ---- per-item tax (demo tariff)
    try:
        tariff_ds = require_dataset(db, "TARIFF")
        rates = dataset_payload(tariff_ds).get("rates", {})
    except ConflictingDatasets as exc:
        tariff_ds, rates = None, {}
        specs.append(IssueSpec("tariff_dataset_conflict", "TARIFF_KNOWLEDGE_CONFLICT", "CRITICAL", "VALUATION", "Xung đột biểu thuế hiệu lực",
                               f"Nhiều dataset cùng hiệu lực; reviewer phải giải quyết. {exc}", auto_resolvable=True))
    except NoActiveDataset:
        tariff_ds, rates = None, {}
        specs.append(IssueSpec("tariff_dataset", "TARIFF_KNOWLEDGE_UNAVAILABLE", "CRITICAL", "VALUATION", "Không có biểu thuế hiệu lực",
                               "Không tính thuế khi thiếu dataset (fail-closed).", auto_resolvable=True))
    for it in items:
        amount = parse_decimal(it.amount)
        share = (amount / basis) if (amount is not None and basis) else None
        item_value = (customs_value * share).quantize(Q) if (customs_value is not None and share is not None) else None
        co = assessments.get(db, case.id, "CO", it.id)
        fta_applied = bool(co and co.reviewer_decision and co.reviewer_decision.get("decision") == "APPLY")
        r = []
        if it.hs_status != "APPROVED" or not it.hs_code:
            assessments.upsert(db, case, "TAX", it.id, status="AWAITING_HS", ds=tariff_ds,
                               inputs={"item_value": str(item_value) if item_value else None, "hs_code": None},
                               result={}, reasoning=["Chưa có HS được duyệt → không tính thuế."])
            continue
        hit = lookup(rates, it.hs_code)  # longest matching key: 8-digit line if present, else the heading (G18B)
        rate_key, rate = hit if hit else (None, None)
        if rate is None:
            assessments.upsert(db, case, "TAX", it.id, status="RATE_NOT_FOUND", ds=tariff_ds,
                               inputs={"hs_code": it.hs_code}, result={}, reasoning=[f"Không có dòng thuế cho mã {it.hs_code} (nhóm {it.hs_code[:4]})."])
            specs.append(IssueSpec(f"tax_rate:item:{it.line_no}", "TARIFF_RATE_NOT_FOUND", "WARNING", "VALUATION",
                                   f"Item {it.line_no}: không tìm thấy thuế suất cho {it.hs_code}", target_ref=f"item:{it.line_no}", auto_resolvable=True))
            continue
        duty_pct = Decimal(str(rate["mfn_duty_pct"]))
        pref = None
        decided_pref = (co.reviewer_decision or {}).get("preferential_duty_pct") if fta_applied else None
        if fta_applied and (decided_pref if decided_pref is not None else co.result.get("preferential_duty_pct")) is not None:
            # the rate the reviewer actually approved (recorded in the decision) wins over a later recomputation (G18C)
            pref = Decimal(str(decided_pref if decided_pref is not None else co.result["preferential_duty_pct"]))
            duty_pct = pref
            r.append(f"Áp dụng thuế suất ưu đãi {pref}% theo quyết định reviewer trên C/O (form {co.inputs.get('form')}).")
        else:
            r.append(f"Thuế suất MFN {duty_pct}% theo dòng {rate_key} ({tariff_ds.version}); chưa áp dụng FTA (chưa có quyết định reviewer).")
        vat_pct = Decimal(str(rate["vat_pct"]))
        if item_value is None:
            assessments.upsert(db, case, "TAX", it.id, status="INPUT_MISSING", ds=tariff_ds,
                               inputs={"hs_code": it.hs_code, "duty_pct": str(duty_pct), "vat_pct": str(vat_pct)}, result={},
                               reasoning=r + ["Thiếu trị giá tính thuế."])
            continue
        duty = (item_value * duty_pct / 100).quantize(Q, ROUND_HALF_UP)
        vat = ((item_value + duty) * vat_pct / 100).quantize(Q, ROUND_HALF_UP)
        assessments.upsert(db, case, "TAX", it.id, status="COMPUTED", ds=tariff_ds,
                           inputs={"hs_code": it.hs_code, "item_value": str(item_value), "duty_pct": str(duty_pct), "vat_pct": str(vat_pct),
                                   "fta_applied": fta_applied},
                           result={"import_duty": str(duty), "vat": str(vat), "total_tax": str(duty + vat), "currency": currency,
                                   "label": tariff_ds.label if tariff_ds else None},
                           reasoning=r + [f"Thuế NK = {item_value} × {duty_pct}% = {duty}; VAT = ({item_value}+{duty}) × {vat_pct}% = {vat}."])
    sync(db, case, specs, "valuation")
