import { render, screen, waitFor } from "@testing-library/react";
import { Goods } from "./Goods";
import type { Ctx } from "../App";

const ctx: Ctx = {
  me: { user: { id: "u", email: "o@t", full_name: "O", role: "OPERATOR", tenant_id: "t" }, permissions: ["case.read"] },
  caseId: "c1", cases: [], can: () => false, toast: () => undefined, go: () => undefined, refreshCases: async () => undefined, selectCase: () => undefined, bump: 0, refresh: () => undefined,
};

test("goods table shows BLOCKED badge and confidence for the low-evidence item", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes("/items")
      ? [{ id: "i3", line_no: 3, description: "Electrical controller", description_vn: null, description_vn_status: "NEEDS_REVIEW", model: "CT-88", quantity: "15", unit: "SET", unit_price: "32.00", amount: "480.00", attributes: {}, hs_code: null, hs_status: "BLOCKED", hs_confidence: 0.64, co_line_matched: null, origin_criterion: null, source_ref: "invoice.txt#line=14",
          candidates: [{ id: "k", rank: 1, heading: "8537", title: "Boards, panels", confidence: 0.64, reasoning: ["Khớp từ khóa"], missing_attributes: ["function", "voltage"], history_refs: [{ case_no: "VIP-1", hs_code: "85371099", match: "MODEL", reusable: false, outcome: "CONSULTATION" }], dataset_version: "demo-hs-2026.10", status: "PROPOSED" }] }]
      : [];
    return new Response(JSON.stringify(body), { status: 200 });
  }) as unknown as typeof fetch;
  render(<Goods ctx={ctx} />);
  await waitFor(() => expect(screen.getByText("BLOCKED")).toBeInTheDocument());
  expect(screen.getByText("64%")).toBeInTheDocument();
  expect(screen.getByText("8537.xx.xx")).toBeInTheDocument();
  expect(screen.getByText("Prior consultation")).toBeInTheDocument();
});
