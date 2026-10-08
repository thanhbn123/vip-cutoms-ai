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
         "exclusions": ["vacuum", "air"], "required_attributes": ["application", "power"], "base_confidence": 0.80,
         "notes": "Demo note: distinguish by driving mechanism and application; power/flow data required."},
        {"heading": "8414", "title": "Air or vacuum pumps, compressors, fans", "keywords": ["fan", "compressor", "vacuum pump", "blower"],
         "exclusions": [], "required_attributes": ["application"], "base_confidence": 0.78},
        {"heading": "3917", "title": "Tubes, pipes and hoses of plastics", "keywords": ["pvc pipe", "plastic pipe", "hose", "tube", "pipe"],
         "exclusions": ["steel", "iron", "copper"], "required_attributes": ["material"], "base_confidence": 0.92},
        {"heading": "7304", "title": "Tubes and pipes of iron or steel, seamless", "keywords": ["steel pipe", "steel tube", "seamless pipe"],
         "exclusions": ["pvc", "plastic"], "required_attributes": ["material"], "base_confidence": 0.85},
        {"heading": "8537", "title": "Boards, panels, consoles for electric control", "keywords": ["controller", "control panel", "bộ điều khiển", "control cabinet"],
         "exclusions": [], "required_attributes": ["function", "voltage", "application"], "base_confidence": 0.70,
         "notes": "Demo note: requires two or more apparatus of 8535/8536 and a function description; otherwise consider 8536/8538."},
        {"heading": "8536", "title": "Electrical switching/protecting apparatus (≤1000V)", "keywords": ["switch", "relay", "controller", "fuse", "socket"],
         "exclusions": ["panel", "cabinet"], "required_attributes": ["function", "voltage"], "base_confidence": 0.45},
        {"heading": "8481", "title": "Taps, cocks, valves", "keywords": ["valve", "tap", "cock"], "exclusions": [],
         "required_attributes": ["material", "application"], "base_confidence": 0.82},
        {"heading": "8501", "title": "Electric motors and generators", "keywords": ["motor", "generator"], "exclusions": ["pump"],
         "required_attributes": ["power", "voltage"], "base_confidence": 0.80},
    ],
}
