"""Deterministic mock provider (no network, no credentials).

It parses *structured text* documents (simulated OCR output, see tests/fixtures) with regexes,
assigns deterministic confidence and line-level source references, and answers Copilot
questions from the structured case context only. It never invents facts that are not in the
context: unknown → explicitly reported as unknown.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.base import CopilotAnswer, ExtractedValue, ExtractionResult

HEADER_PATTERNS: dict[str, list[tuple[str, str]]] = {
    # doc_type: [(field key, label regex)]
    "INVOICE": [
        ("invoice.number", r"invoice\s*no\.?"),
        ("invoice.date", r"invoice\s*date|date"),
        ("party.exporter", r"exporter|seller|shipper"),
        ("party.importer", r"importer|buyer|consignee"),
        ("valuation.incoterm", r"incoterms?"),
        ("valuation.currency", r"currency"),
        ("invoice.total_amount", r"total\s*amount|total"),
        ("valuation.freight", r"freight"),
        ("valuation.insurance", r"insurance"),
        ("shipment.total_packages", r"total\s*packages|packages"),
        ("shipment.gross_weight", r"gross\s*weight"),
    ],
    "PACKING_LIST": [
        ("packing.invoice_ref", r"invoice\s*ref|invoice\s*no\.?"),
        ("shipment.total_packages", r"total\s*packages|packages"),
        ("shipment.gross_weight", r"gross\s*weight"),
        ("shipment.net_weight", r"net\s*weight"),
    ],
    "BILL_OF_LADING": [
        ("bl.number", r"b/?l\s*no\.?|bill\s*of\s*lading\s*no\.?"),
        ("bl.date", r"b/?l\s*date|date"),
        ("transport.vessel", r"vessel"),
        ("transport.port_of_loading", r"port\s*of\s*loading"),
        ("transport.port_of_discharge", r"port\s*of\s*discharge"),
        ("shipment.total_packages", r"total\s*packages|packages"),
        ("shipment.gross_weight", r"gross\s*weight"),
        ("party.consignee", r"consignee"),
    ],
    "CO": [
        ("co.form", r"form"),
        ("co.number", r"reference\s*no\.?|c/?o\s*no\.?"),
        ("co.date", r"issued\s*date|date"),
        ("co.exporter", r"exporter"),
        ("co.importer", r"importer|consignee"),
        ("co.invoice_ref", r"invoice\s*ref|invoice\s*no\.?"),
        ("co.origin_country", r"origin\s*country|country\s*of\s*origin"),
    ],
    "CONTRACT": [
        ("contract.number", r"contract\s*no\.?"),
        ("contract.date", r"date"),
        ("party.exporter", r"seller|exporter"),
        ("party.importer", r"buyer|importer"),
    ],
    "CATALOGUE": [
        ("catalogue.model", r"model"),
        ("catalogue.function", r"function|use"),
        ("catalogue.voltage", r"voltage"),
        ("catalogue.power", r"power"),
        ("catalogue.application", r"application|used\s*(in|for)"),
    ],
}

# Item tables: "ITEMS" header then pipe-separated rows.
ITEM_COLUMNS: dict[str, list[str]] = {
    "INVOICE": ["line_no", "description", "model", "quantity", "unit", "unit_price", "amount"],
    "PACKING_LIST": ["line_no", "description", "model", "quantity", "unit", "packages"],
    "CO": ["line_no", "description", "model", "quantity", "unit", "origin_criterion"],
}


def _confidence_for(value: str, base: float) -> float:
    # deterministic: shorter/ambiguous values get a lower score; empty → 0
    if not value:
        return 0.0
    penalty = 0.04 if len(value) < 3 else 0.0
    penalty += 0.05 if "?" in value else 0.0
    return round(max(0.0, min(1.0, base - penalty)), 2)


class MockProvider:
    name = "mock"
    version = "mock-1.0.0"

    # ------------------------------------------------------------------ extraction
    def extract_document(self, doc_type: str, filename: str, content: bytes) -> ExtractionResult:
        result = ExtractionResult(doc_type=doc_type, provider=self.name, provider_version=self.version)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            result.warnings.append("Binary/scanned document: mock provider cannot OCR it; manual review required")
            return result

        lines = text.splitlines()
        patterns = HEADER_PATTERNS.get(doc_type, [])
        taken: set[str] = set()
        in_items = False
        columns = ITEM_COLUMNS.get(doc_type)
        for idx, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line:
                continue
            if line.upper().startswith("ITEMS"):
                in_items = True
                continue
            if in_items and columns and "|" in line:
                cells = [c.strip() for c in line.split("|")]
                if len(cells) != len(columns):
                    result.warnings.append(f"line {idx}: item row has {len(cells)} cells, expected {len(columns)}")
                    continue
                n = cells[0]
                for col, cell in zip(columns[1:], cells[1:], strict=True):
                    result.values.append(
                        ExtractedValue(
                            key=f"items[{n}].{col}",
                            value=cell,
                            confidence=_confidence_for(cell, 0.95),
                            source_ref=f"{filename}#line={idx}",
                            method="mock.table-row",
                        )
                    )
                continue
            if ":" not in line:
                continue
            in_items = False
            label, _, value = line.partition(":")
            label_l = label.strip().lower()
            value = value.strip()
            for key, rx in patterns:
                if key in taken:
                    continue
                if re.fullmatch(rx, label_l):
                    taken.add(key)
                    result.values.append(
                        ExtractedValue(
                            key=key,
                            value=value,
                            confidence=_confidence_for(value, 0.98),
                            source_ref=f"{filename}#line={idx}",
                            method="mock.key-value",
                        )
                    )
                    break
        if not result.values:
            result.warnings.append("No recognisable fields; document requires manual review")
        return result

    # ------------------------------------------------------------------ description
    def propose_description(self, item: dict[str, Any]) -> tuple[str, list[str]]:
        parts: list[str] = []
        reasoning: list[str] = []
        desc = item.get("description_vn") or item.get("description") or ""
        if desc:
            parts.append(desc.rstrip(". "))
            reasoning.append("Mô tả gốc từ Invoice (" + str(item.get("source_ref") or "invoice") + ")")
        if item.get("model") and str(item["model"]).lower() not in desc.lower():
            parts.append(f"model {item['model']}")
            reasoning.append("Bổ sung model từ Invoice")
        attrs = item.get("attributes") or {}
        for k in ("function", "application", "voltage", "power", "material"):
            if attrs.get(k):
                parts.append(f"{k}: {attrs[k]}")
                reasoning.append(f"Thuộc tính '{k}' từ dữ liệu kỹ thuật đã có trong hồ sơ")
        parts.append("hàng mới 100%")
        reasoning.append("'hàng mới 100%' là giả định mặc định — reviewer phải xác nhận")
        return ", ".join(parts) + ".", reasoning

    # ------------------------------------------------------------------ copilot
    def answer_case_question(self, question: str, context: dict[str, Any]) -> CopilotAnswer:
        from app.ai.copilot_templates import answer

        return answer(question, context, provider=self.name)
