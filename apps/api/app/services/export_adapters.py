"""Export adapters. Only INTERNAL formats exist in the MVP; an external customs adapter (e.g. VNACCS) would implement
`ExportAdapter` behind an explicit owner-approved integration gate (G14). No such adapter is shipped."""

from __future__ import annotations

import csv
import io
import json
from typing import Protocol


class ExportAdapter(Protocol):
    name: str
    content_type: str

    def render(self, payload: dict) -> bytes: ...


class InternalJsonAdapter:
    name = "internal-json"
    content_type = "application/json"

    def render(self, payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


class InternalCsvAdapter:
    """Line-item CSV (UTF-8 BOM for spreadsheet tools). Header row carries the watermark."""

    name = "internal-csv"
    content_type = "text/csv; charset=utf-8"

    def render(self, payload: dict) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"# {payload['meta']['watermark']} · {payload['case']['case_no']} · v{payload['meta']['version']} · {payload['meta']['schema_version']}"])
        w.writerow(["line_no", "description", "description_vn", "model", "quantity", "unit", "unit_price", "amount", "hs_code", "hs_status",
                    "origin_criterion", "fta_decision", "duty_pct", "import_duty", "vat", "policy_status"])
        for it in payload["items"]:
            tax = it.get("tax") or {}
            w.writerow([it["line_no"], it["description"], it.get("description_vn") or "", it.get("model") or "", it.get("quantity") or "",
                        it.get("unit") or "", it.get("unit_price") or "", it.get("amount") or "", it["hs"]["code"] or "", it["hs"]["status"],
                        it["origin"].get("criterion") or "", (it["origin"].get("reviewer_decision") or {}).get("decision") or "",
                        (tax.get("inputs") or {}).get("duty_pct") or "", (tax.get("result") or {}).get("import_duty") or "",
                        (tax.get("result") or {}).get("vat") or "", (it.get("policy") or {}).get("status") or ""])
        return ("﻿" + buf.getvalue()).encode("utf-8")


ADAPTERS: dict[str, ExportAdapter] = {"json": InternalJsonAdapter(), "csv": InternalCsvAdapter()}
