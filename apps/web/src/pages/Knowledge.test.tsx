import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Knowledge } from "./Knowledge";
import type { Ctx } from "../App";

function ctxWith(perms: string[]): Ctx {
  return {
    me: { user: { id: "u", email: "a@t", full_name: "A", role: "ADMIN", tenant_id: "t" }, permissions: perms },
    caseId: null, cases: [], can: (p) => perms.includes(p), toast: () => undefined, go: () => undefined, refreshCases: async () => undefined, selectCase: () => undefined, bump: 0, refresh: () => undefined,
  };
}

const datasets = [
  { id: "d1", kind: "TARIFF", version: "demo-tariff-2026.10", label: "Demo", source: "fixtures", is_demo: true, effective_from: "2026-01-01", effective_to: null, is_active: true, rule_count: 8, is_authoritative: false },
  { id: "d2", kind: "TARIFF", version: "mfn-2026-01", label: "MFN 2026", source: "https://x", is_demo: false, effective_from: "2026-01-01", effective_to: null, is_active: false, rule_count: 1,
    is_authoritative: false, source_authority: "Authority", source_document: "Decision 1/2026", source_reference: "https://x", checksum: "abcdef0123456789" },
  { id: "d3", kind: "POLICY", version: "pol-2026", label: "Policy", source: "https://y", is_demo: false, effective_from: "2026-01-01", effective_to: null, is_active: true, rule_count: 0,
    is_authoritative: true, verified_at: "2026-10-09T00:00:00Z", source_authority: "Authority", source_document: "Circular 2/2026", source_reference: "https://y", checksum: "fedcba9876543210" },
];

function mockFetch(calls: string[]) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (url.includes("/knowledge/notice")) return new Response(JSON.stringify({ demo_active: true, notice: "DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING", datasets: ["TARIFF demo-tariff-2026.10"], non_demo_datasets: [], app_mode: "limited", authoritative_datasets: ["POLICY pol-2026"] }), { status: 200 });
    if (url.includes("/knowledge/datasets/d2") && !url.includes("verify")) return new Response(JSON.stringify({ ...datasets[1], provenance_problems: [], payload: { rates: {} } }), { status: 200 });
    if (url.includes("/verify")) return new Response(JSON.stringify({ ...datasets[1], is_authoritative: true, verified_at: "2026-10-09T01:00:00Z" }), { status: 200 });
    if (url.includes("/knowledge/datasets")) return new Response(JSON.stringify(datasets), { status: 200 });
    return new Response("{}", { status: 200 });
  }) as unknown as typeof fetch;
}

test("admin sees provenance, authoritative badges, verify/import actions; verify posts a reason", async () => {
  const calls: string[] = [];
  mockFetch(calls);
  vi.spyOn(window, "prompt").mockReturnValue("checked against gazette");
  render(<Knowledge ctx={ctxWith(["knowledge.manage", "knowledge.verify"])} />);
  await waitFor(() => expect(screen.getByText("authoritative")).toBeInTheDocument());
  expect(screen.getAllByText("demo").length).toBe(1);
  expect(screen.getByText("chưa xác minh")).toBeInTheDocument();
  expect(screen.getByText(/Authority · Decision 1\/2026/)).toBeInTheDocument();
  expect(screen.getByText("Import gói dữ liệu (JSON)")).toBeInTheDocument();
  // only the unverified non-demo dataset offers "xác minh"
  const verifyLinks = screen.getAllByText("xác minh");
  expect(verifyLinks.length).toBe(1);
  fireEvent.click(verifyLinks[0]);
  await waitFor(() => expect(calls.some((c) => c === "POST /api/v1/knowledge/datasets/d2/verify")).toBe(true));
});

test("a reviewer sees provenance but no management actions", async () => {
  mockFetch([]);
  render(<Knowledge ctx={ctxWith(["case.read"])} />);
  await waitFor(() => expect(screen.getByText("authoritative")).toBeInTheDocument());
  expect(screen.queryByText("xác minh")).toBeNull();
  expect(screen.queryByText("Import gói dữ liệu (JSON)")).toBeNull();
  expect(screen.queryByText("thay thế")).toBeNull();
});

test("the demo warning stays when the notice endpoint fails (fail closed)", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/knowledge/notice")) return new Response("boom", { status: 500 });
    if (url.includes("/knowledge/datasets")) return new Response(JSON.stringify([datasets[2]]), { status: 200 });  // only an authoritative POLICY set
    return new Response("{}", { status: 200 });
  }) as unknown as typeof fetch;
  render(<Knowledge ctx={ctxWith(["case.read"])} />);
  await waitFor(() => expect(screen.getByText("authoritative")).toBeInTheDocument());
  expect(screen.getByText("DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING")).toBeInTheDocument();
});
