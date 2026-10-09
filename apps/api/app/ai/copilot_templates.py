"""Deterministic Copilot answers for the mock provider. Uses ONLY the structured case context passed in.

Each answer returns sources (ids that exist in the context) and reasoning steps. Unknown → stated as unknown.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.base import CopilotAnswer


def _item_no(q: str) -> int | None:
    m = re.search(r"(?:item|dòng|mục|hàng)\s*#?\s*(\d+)", q)
    return int(m.group(1)) if m else None


def detect_intent(q: str) -> str:
    s = q.lower()
    if any(k in s for k in ("mô tả", "description", "describe", "đề xuất mô tả")):
        return "DESCRIBE"
    if any(k in s for k in ("form e", "form d", "c/o", "co ", "xuất xứ", "origin", "fta")):
        return "CO"
    if any(k in s for k in ("trị giá", "tri gia", "giá", "valuation", "bất thường", "price", "value")):
        return "VALUATION"
    if any(k in s for k in ("thiếu", "còn gì", "cần gì", "missing", "để khai", "checklist")):
        return "MISSING"
    if re.search(r"\bhs\b|mã số|phân loại|classif", s):
        return "HS_WHY"
    return "GENERAL"


def _src(kind: str, id_: str, label: str) -> dict[str, str]:
    return {"type": kind, "id": str(id_), "label": label}


def answer(question: str, ctx: dict[str, Any], provider: str) -> CopilotAnswer:
    intent = detect_intent(question)
    items = {i["line_no"]: i for i in ctx["items"]}
    issues = ctx["issues"]
    sources: list[dict] = []
    reasoning: list[str] = []
    n = _item_no(question.lower())

    if intent == "MISSING":
        crit = [i for i in issues if i["severity"] == "CRITICAL"]
        warn = [i for i in issues if i["severity"] != "CRITICAL"]
        lines = [f"Hồ sơ {ctx['case']['case_no']} đang ở trạng thái {ctx['case']['status']}: {len(crit)} critical, {len(warn)} warning."]
        for i in crit:
            lines.append(f"🔴 {i['title']}" + (f" — {i['detail']}" if i.get("detail") else ""))
            sources.append(_src("issue", i["id"], i["code"]))
        for i in warn:
            lines.append(f"🟠 {i['title']}")
            sources.append(_src("issue", i["id"], i["code"]))
        pending_hs = [f"Item {it['line_no']}" for it in ctx["items"] if it["hs"]["status"] != "APPROVED"]
        if pending_hs:
            lines.append("HS chưa được reviewer duyệt: " + ", ".join(pending_hs) + ".")
        unapproved = [f["label"] for f in ctx["fields"] if f["is_critical"] and f["review_status"] not in ("APPROVED",)]
        if unapproved:
            lines.append(f"Trường critical chờ duyệt: {', '.join(unapproved[:8])}" + (" …" if len(unapproved) > 8 else "") + ".")
        if crit:
            lines.append("Các critical phải được xử lý trước; hệ thống không phát hành khi còn BLOCKED.")
        elif not issues and not pending_hs and not unapproved:
            lines.append("Không còn việc mở — reviewer có thể đánh dấu READY_TO_EXPORT.")
        reasoning += ["Đọc danh sách issue mở theo mức độ.", "Đối chiếu trạng thái HS từng dòng hàng và trạng thái duyệt của trường critical.",
                      "Áp quy tắc fail-closed: còn critical → không phát hành."]
        actions = [f"Xử lý: {i['title']}" for i in crit] + ([f"Reviewer duyệt HS: {', '.join(pending_hs)}"] if pending_hs else []) \
            + (["Reviewer duyệt các trường critical (Smart Declaration → Duyệt tất cả)"] if unapproved else []) \
            + [f"Resolve/waive: {i['title']}" for i in warn[:5]]
        return CopilotAnswer("\n".join(lines), intent, sources, reasoning, provider, confidence=0.95,
                             recommended_actions=actions or ["Đánh dấu READY_TO_EXPORT"], requires_review=bool(crit or pending_hs or unapproved))

    if intent == "HS_WHY":
        targets = [items[n]] if n in items else ctx["items"]
        lines = []
        for it in targets:
            hs = it["hs"]
            if hs["status"] == "APPROVED":
                lines.append(f"Item {it['line_no']} ({it['model'] or it['description']}): HS {hs['code']} đã được reviewer duyệt.")
            elif hs["candidates"]:
                top = hs["candidates"][0]
                lines.append(f"Item {it['line_no']} ({it['model'] or it['description']}): ứng viên {top['heading']} — {top['title']}, confidence {top['confidence']:.0%}, trạng thái {hs['status']}.")
                lines += [f"  • {r}" for r in top["reasoning"]]
                if top["missing_attributes"]:
                    lines.append(f"  • Để chốt cần bổ sung: {', '.join(top['missing_attributes'])} (catalogue / thông số kỹ thuật).")
                if len(hs["candidates"]) > 1:
                    lines.append("  • Ứng viên khác: " + "; ".join(f"{c['heading']} ({c['confidence']:.0%})" for c in hs["candidates"][1:]))
                if it.get("history"):
                    for h in it["history"]:
                        lines.append(f"  • Lịch sử: {h['case_no']} đã duyệt {h['hs_code']} ({h['match']}, outcome {h['outcome']})" + ("" if h["reusable"] else " — KHÔNG tự áp dụng (từng tham vấn/tranh chấp)."))
                        sources.append(_src("memory", h["memory_id"], h["case_no"]))
                sources.append(_src("hs_candidate", top["id"], f"{top['heading']} · {top['dataset_version']}"))
                lines.append("  • Hệ thống chỉ đề xuất; mã 8 số do reviewer chốt và phải được duyệt trước khi phát hành.")
            else:
                lines.append(f"Item {it['line_no']}: chưa có ứng viên HS (không quy tắc nào khớp) → cần phân loại thủ công.")
            if it.get("source_document_id"):
                sources.append(_src("document", it["source_document_id"], it.get("source_ref") or "invoice"))
        reasoning += ["Lấy ứng viên HS từ engine quy tắc (dataset có phiên bản/hiệu lực).", "Giải thích theo từ khóa khớp, thuộc tính kỹ thuật có/thiếu và lịch sử đã duyệt.",
                      "Không tự chốt HS: critical field cần reviewer."]
        actions, unapproved_items = [], [it for it in targets if it["hs"]["status"] != "APPROVED"]
        for it in unapproved_items:
            top = it["hs"]["candidates"][0] if it["hs"]["candidates"] else None
            if top and top["missing_attributes"]:
                actions.append(f"Item {it['line_no']}: bổ sung {', '.join(top['missing_attributes'])} (catalogue/ảnh nhãn) rồi chạy lại AI")
            actions.append(f"Item {it['line_no']}: reviewer chốt mã 8 số" + (f" trong nhóm {top['heading']}" if top else " thủ công"))
        conf = 0.9 if all(it["hs"]["candidates"] for it in targets) else 0.5
        return CopilotAnswer("\n".join(lines), intent, sources, reasoning, provider, confidence=conf, recommended_actions=actions,
                             requires_review=bool(unapproved_items))

    if intent == "CO":
        co_issues = [i for i in issues if i["category"] == "CO" or i["code"].startswith("CO_")]
        lines = []
        if not ctx.get("co_document"):
            lines.append("Hồ sơ chưa có C/O → mọi dòng hàng áp thuế suất thông thường.")
        else:
            d = ctx["co_document"]
            lines.append(f"C/O {d['doc_type']} v{d['version']} đã parse ({d['parse_confidence']:.0%}).")
            sources.append(_src("document", d["id"], "C/O"))
        for it in ctx["items"]:
            o = it["origin"]
            if o and o.get("status"):
                lines.append(f"Item {it['line_no']}: {o['status']}" + (f" — ưu đãi {o['preferential_duty_pct']}%" if o.get("preferential_duty_pct") is not None else "")
                             + (f"; quyết định reviewer: {o['reviewer_decision']['decision']}" if o.get("reviewer_decision") else "; chưa có quyết định reviewer"))
        for i in co_issues:
            lines.append(f"🟠 {i['title']}" + (f" — {i['detail']}" if i.get("detail") else ""))
            sources.append(_src("issue", i["id"], i["code"]))
        lines.append("FTA chỉ được áp dụng sau khi reviewer quyết định trên từng dòng hàng.")
        reasoning += ["Đọc trạng thái đánh giá C/O từng dòng (dataset FTA có phiên bản).", "Liệt kê issue liên quan C/O.", "Không tự áp dụng ưu đãi."]
        pending = [it for it in ctx["items"] if (it["origin"] or {}).get("status") == "ELIGIBLE_PENDING_REVIEW" and not (it["origin"] or {}).get("reviewer_decision")]
        actions = [f"Xử lý: {i['title']}" for i in co_issues if i["code"] != "CO_DECISION_PENDING"] + [f"Item {it['line_no']}: reviewer quyết định áp dụng C/O" for it in pending]
        return CopilotAnswer("\n".join(lines), intent, sources, reasoning, provider, confidence=0.9 if ctx.get("co_document") else 0.8,
                             recommended_actions=actions, requires_review=bool(co_issues or pending))

    if intent == "VALUATION":
        v = ctx.get("valuation") or {}
        lines = [f"Trị giá: trạng thái {v.get('status', 'chưa đánh giá')}."]
        for r in v.get("reasoning", []):
            lines.append("  • " + r)
        if v.get("result", {}).get("customs_value"):
            lines.append(f"  • Trị giá tính thuế tính toán: {v['result']['customs_value']} {v['result'].get('currency') or ''}.")
        val_issues = [i for i in issues if i["category"] == "VALUATION"]
        for i in val_issues:
            lines.append(f"🟠 {i['title']}" + (f" — {i['detail']}" if i.get("detail") else ""))
            sources.append(_src("issue", i["id"], i["code"]))
        compared = False
        for it in ctx["items"]:
            for h in it.get("history", []):
                if h.get("unit_price") and it.get("unit_price"):
                    try:
                        prev, cur = float(h["unit_price"]), float(it["unit_price"])
                        delta = (cur - prev) / prev * 100 if prev else 0
                        flag = "bất thường (>15%)" if abs(delta) > 15 else "bình thường"
                        lines.append(f"Item {it['line_no']}: đơn giá {cur} so với lịch sử {prev} ({h['case_no']}): {delta:+.1f}% — {flag}.")
                        sources.append(_src("memory", h["memory_id"], h["case_no"]))
                        compared = True
                    except ValueError:
                        pass
        if not compared:
            lines.append("Không có dữ liệu lịch sử đã duyệt để so sánh đơn giá; không phát hiện bất thường từ dữ liệu hiện có.")
        reasoning += ["Lấy đánh giá VALUATION (số học xác định trên các trường đã map/duyệt).", "So sánh đơn giá với bộ nhớ đã duyệt cùng model nếu có."]
        actions = [f"Xử lý: {i['title']}" for i in val_issues] + [f"Reviewer duyệt {f['label']}" for f in ctx["fields"] if f["is_critical"]
                                                                  and f["key"].startswith(("valuation.", "invoice.total")) and f["review_status"] != "APPROVED"]
        return CopilotAnswer("\n".join(lines), intent, sources, reasoning, provider, confidence=0.9 if v.get("status") == "COMPUTED" else 0.6,
                             recommended_actions=actions, requires_review=bool(actions))

    if intent == "DESCRIBE":
        it = items.get(n) if n else (ctx["items"][0] if ctx["items"] else None)
        if not it:
            return CopilotAnswer("Không xác định được dòng hàng. Hãy hỏi kèm số dòng, ví dụ: 'đề xuất mô tả item 1'.", intent, [], ["Không có item"], provider,
                                 confidence=0.0, recommended_actions=["Hỏi lại kèm số dòng"], requires_review=False)
        from app.ai.mock_provider import MockProvider

        proposed, why = MockProvider().propose_description({"description": it["description"], "description_vn": it["description_vn"], "model": it["model"],
                                                            "attributes": {k: v["value"] for k, v in (it["attributes"] or {}).items()},
                                                            "source_ref": it.get("source_ref")})
        if it.get("source_document_id"):
            sources.append(_src("document", it["source_document_id"], it.get("source_ref") or "invoice"))
        lines = [f"Đề xuất mô tả khai báo cho Item {it['line_no']}:", f"“{proposed}”", "Đây là đề xuất — chỉ áp dụng sau khi reviewer duyệt."]
        return CopilotAnswer("\n".join(lines), intent, sources, why, provider,
                             proposal={"target_type": "ITEM_DESCRIPTION_VN", "target_ref": it["id"], "current_value": it["description_vn"],
                                       "proposed_value": proposed},
                             confidence=0.7 if it.get("attributes") else 0.6,
                             recommended_actions=["Reviewer duyệt/từ chối đề xuất trong Approval Queue", "Bổ sung thuộc tính kỹ thuật nếu mô tả còn thiếu"],
                             requires_review=True)

    crit = sum(i["severity"] == "CRITICAL" for i in issues)
    lines = [f"Hồ sơ {ctx['case']['case_no']}: {len(ctx['items'])} dòng hàng, {len(ctx['documents'])} chứng từ, {crit} critical / {len(issues) - crit} warning mở, readiness {ctx['readiness']}%.",
             "Có thể hỏi: 'còn thiếu gì để khai?', 'vì sao HS item 3?', 'Form E có vấn đề gì?', 'trị giá có bất thường không?', 'đề xuất mô tả item 1'.",
             "Mọi dữ liệu không chắc chắn được đánh dấu NEEDS_REVIEW/BLOCKED; AI không tự chốt HS, C/O, trị giá hay chính sách."]
    for d in ctx["documents"]:
        sources.append(_src("document", d["id"], f"{d['doc_type']} v{d['version']}"))
    reasoning += ["Tóm tắt từ trạng thái hồ sơ, issue mở và chứng từ hiện tại."]
    return CopilotAnswer("\n".join(lines), intent, sources, reasoning, provider, confidence=0.8,
                         recommended_actions=["Hỏi 'còn thiếu gì để khai?' để lấy checklist"], requires_review=crit > 0)
