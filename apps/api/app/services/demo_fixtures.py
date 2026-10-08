"""DEMO / FIXTURE knowledge. NON-AUTHORITATIVE. Not Vietnamese law, not a tariff schedule.

Every dataset seeded from here carries is_demo=True and the label below. Replacing these with an
owner-approved authoritative source is BLOCKED_OWNER B-02 (see docs/STATUS.md).
"""

DEMO_LABEL = "DEMO — NON-AUTHORITATIVE FIXTURE"
DEMO_SOURCE = "apps/api/app/services/demo_fixtures.py (hand-written illustrative data)"

HS_RULES_DEMO = {
    "version": "demo-hs-2026.10",
    "effective_from": "2026-01-01",
    "rules": [
        {"heading": "8413", "title": "Pumps for liquids", "keywords": ["pump", "máy bơm", "bơm"],
         "exclusions": ["vacuum", "air"], "required_attributes": ["application", "power"], "base_confidence": 0.85,
         "notes": "Demo note: distinguish by driving mechanism and application; power/flow data required."},
        {"heading": "8414", "title": "Air or vacuum pumps, compressors, fans", "keywords": ["fan", "compressor", "vacuum pump", "blower"],
         "exclusions": [], "required_attributes": ["application"], "base_confidence": 0.78},
        {"heading": "3917", "title": "Tubes, pipes and hoses of plastics", "keywords": ["pvc pipe", "plastic pipe", "hose", "tube"],
         "exclusions": ["steel", "iron", "copper"], "required_attributes": ["material"], "base_confidence": 0.90},
        {"heading": "7304", "title": "Tubes and pipes of iron or steel, seamless", "keywords": ["steel pipe", "steel tube", "seamless pipe"],
         "exclusions": ["pvc", "plastic"], "required_attributes": ["material"], "base_confidence": 0.85},
        {"heading": "8537", "title": "Boards, panels, consoles for electric control", "keywords": ["controller", "control panel", "bộ điều khiển", "control cabinet"],
         "exclusions": [], "required_attributes": ["function", "voltage", "application"], "base_confidence": 0.73,
         "notes": "Demo note: requires two or more apparatus of 8535/8536 and a function description; otherwise consider 8536/8538."},
        {"heading": "8536", "title": "Electrical switching/protecting apparatus (≤1000V)", "keywords": ["switch", "relay", "controller", "fuse", "socket"],
         "exclusions": ["panel", "cabinet"], "required_attributes": ["function", "voltage"], "base_confidence": 0.45},
        {"heading": "8481", "title": "Taps, cocks, valves", "keywords": ["valve", "tap", "cock"], "exclusions": [],
         "required_attributes": ["material", "application"], "base_confidence": 0.82},
        {"heading": "8501", "title": "Electric motors and generators", "keywords": ["motor", "generator"], "exclusions": ["pump"],
         "required_attributes": ["power", "voltage"], "base_confidence": 0.80},
    ],
}

# Illustrative percentages only. NOT a tariff schedule. Replace via BLOCKED_OWNER B-02.
TARIFF_DEMO = {
    "version": "demo-tariff-2026.10",
    "effective_from": "2026-01-01",
    "rates": {  # heading → {mfn_duty_pct, vat_pct}
        "8413": {"mfn_duty_pct": 10.0, "vat_pct": 10.0},
        "8414": {"mfn_duty_pct": 10.0, "vat_pct": 10.0},
        "3917": {"mfn_duty_pct": 5.0, "vat_pct": 10.0},
        "7304": {"mfn_duty_pct": 10.0, "vat_pct": 10.0},
        "8537": {"mfn_duty_pct": 3.0, "vat_pct": 10.0},
        "8536": {"mfn_duty_pct": 5.0, "vat_pct": 10.0},
        "8481": {"mfn_duty_pct": 10.0, "vat_pct": 10.0},
        "8501": {"mfn_duty_pct": 5.0, "vat_pct": 10.0},
    },
}

FTA_DEMO = {
    "version": "demo-fta-2026.10",
    "effective_from": "2026-01-01",
    "forms": {
        "E": {
            "agreement": "ACFTA (demo)",
            "origin_countries": ["CN"],
            "allowed_criteria": ["WO", "PE", "RVC40", "CTH", "PSR"],
            "preferential_duty_pct": {"8413": 0.0, "3917": 0.0, "8537": 0.0, "8536": 0.0, "8501": 0.0, "8414": 0.0, "8481": 0.0, "7304": 5.0},
            "checks": ["exporter_matches_invoice", "importer_matches_invoice", "invoice_ref_matches", "origin_country_allowed",
                       "line_description_matches", "origin_criterion_allowed"],
        },
        "D": {"agreement": "ATIGA (demo)", "origin_countries": ["TH", "MY", "ID", "SG", "PH", "KH", "LA", "MM", "BN"],
              "allowed_criteria": ["WO", "PE", "RVC40", "CTC"], "preferential_duty_pct": {}, "checks": []},
    },
}

POLICY_DEMO = {
    "version": "demo-policy-2026.10",
    "effective_from": "2026-01-01",
    "requirements": {  # heading → list of demo specialized-management requirements
        "8537": [{"code": "QC-ELEC", "title": "Kiểm tra chất lượng thiết bị điện (DEMO)",
                  "evidence_doc_types": ["CATALOGUE"], "needs_reviewer_confirmation": True,
                  "notes": "Demo rule: electrical control equipment may be subject to quality inspection; confirm scope by function/voltage."}],
        "8536": [{"code": "QC-ELEC", "title": "Kiểm tra chất lượng thiết bị điện (DEMO)", "evidence_doc_types": ["CATALOGUE"],
                  "needs_reviewer_confirmation": True}],
        "8413": [{"code": "EE-CHECK", "title": "Rà soát hiệu suất năng lượng động cơ bơm (DEMO)", "evidence_doc_types": [],
                  "needs_reviewer_confirmation": True}],
        "8501": [{"code": "EE-LABEL", "title": "Nhãn năng lượng động cơ điện (DEMO)", "evidence_doc_types": ["CATALOGUE"],
                  "needs_reviewer_confirmation": True}],
    },
}
