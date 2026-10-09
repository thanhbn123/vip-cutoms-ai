import { render, screen, waitFor } from "@testing-library/react";
import { Manage } from "./Manage";
import type { Ctx } from "../App";

const ctx: Ctx = {
  me: { user: { id: "u", email: "a@t", full_name: "A", role: "ADMIN", tenant_id: "t" }, permissions: ["case.read", "audit.read", "user.manage"] },
  caseId: null, cases: [], can: (p) => ["case.read", "audit.read", "user.manage"].includes(p), toast: () => undefined, go: () => undefined, refreshCases: async () => undefined, selectCase: () => undefined, bump: 0, refresh: () => undefined,
};

test("admin page renders the structured readiness panel from /ready", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/ready")) return new Response(JSON.stringify({
      status: "not_ready", mode: "full", blocking: ["document_ai: mock provider not allowed in full mode", "backup status missing"],
      checks: { environment: "production", release_sha: "dd3c12984c49", database: "ok", migrations: "0012_ai_usage_events", migration_head: "0012_ai_usage_events", migration_in_sync: true,
        providers: { document_ocr: { name: "mock", configured: true, healthy: true, is_mock: true, detail: "" }, document_ai: { name: "http-llm", configured: true, healthy: false, is_mock: false, detail: "probe failed" } },
        customs_data_authoritative: { TARIFF: { authoritative: true, version: "mfn-2026-01" }, HS_RULES: { authoritative: false, reason: "none" }, all_authoritative: false, error: "ProgrammingError" },
        backup_status: { state: "missing" } },
    }), { status: 503 });
    if (url.includes("/dashboard/summary")) return new Response(JSON.stringify({ cases_by_status: { BLOCKED: 2 }, open_issues: { CRITICAL: 3 }, fields_total: 10, fields_accepted_pct: 50, drafts_exported: 1 }), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  }) as unknown as typeof fetch;
  render(<Manage ctx={ctx} />);
  await waitFor(() => expect(screen.getByTestId("readiness")).toBeInTheDocument());
  expect(screen.getByText(/not_ready · FULL/)).toBeInTheDocument();
  expect(screen.getByText(/OCR: mock \(mock\)/)).toBeInTheDocument();
  expect(screen.getByText(/Trích xuất: http-llm ✗/)).toBeInTheDocument();
  expect(screen.getByText(/TARIFF: authoritative/)).toBeInTheDocument();
  expect(screen.getByText(/HS_RULES: demo\/chưa xác minh/)).toBeInTheDocument();
  expect(screen.getByText(/lỗi ProgrammingError/)).toBeInTheDocument();
  expect(screen.queryByText(/error: demo/)).toBeNull();
  expect(screen.getByText("document_ai: mock provider not allowed in full mode")).toBeInTheDocument();
  expect(screen.getByText(/Backup off-host:/).closest("p")).toHaveTextContent("missing");
});
