# DEMO FIXTURE — not real trade documents

Simulated OCR text for the V12 reference case (Minh Phát / Guangzhou ABC, INV-2026-889, 3 items).
Deliberate issues: package count 124 (Invoice) vs 126 (Packing List/B/L); Form E item 1 missing model;
item 3 (CT-88) has no technical data until `catalogue_ct88.txt` is supplied; insurance 100 is stated on the invoice but is a
critical field → NEEDS_REVIEW. Owner scenario: invoice 17,900 + freight 420 + insurance 100 = CIF 18,420; line amounts sum to
1,980 so INVOICE_TOTAL_MISMATCH is raised deliberately (see DECISIONS D-007).
