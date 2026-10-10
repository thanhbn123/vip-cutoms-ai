import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

test("admin manages the tenant's users: create, re-role, deactivate, reset password — all through the audited API", async () => {
  const calls: { method: string; url: string; body: unknown }[] = [];
  const users = [
    { id: "u", email: "a@t", full_name: "A", role: "ADMIN", tenant_id: "t", is_active: true },
    { id: "u2", email: "op@t", full_name: "Op", role: "OPERATOR", tenant_id: "t", is_active: true },
    { id: "u3", email: "gone@t", full_name: "Gone", role: "REVIEWER", tenant_id: "t", is_active: false },
  ];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/ready")) return new Response(JSON.stringify({ status: "ready", checks: {} }), { status: 200 });
    if (url.includes("/dashboard/summary")) return new Response(JSON.stringify({ cases_by_status: {}, open_issues: {}, fields_total: 0, fields_accepted_pct: 0, drafts_exported: 0 }), { status: 200 });
    if (url.endsWith("/users") && method === "GET") return new Response(JSON.stringify(users), { status: 200 });
    if (url.endsWith("/users") && method === "POST") return new Response(JSON.stringify({ ...users[1], id: "u4" }), { status: 201 });
    if (url.includes("/reset-password")) return new Response(null, { status: 204 });
    if (url.includes("/users/") && method === "PATCH") return new Response(JSON.stringify(users[1]), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  }) as unknown as typeof fetch;
  render(<Manage ctx={ctx} />);
  await waitFor(() => expect(screen.getByText("op@t")).toBeInTheDocument());
  expect(screen.getByText("inactive")).toBeInTheDocument();
  expect(screen.getByText("(bạn)")).toBeInTheDocument();  // no self-deactivate / self-re-role controls
  expect(screen.queryByLabelText("Vai trò a@t")).toBeNull();
  // deactivate op (reason prompt)
  vi.spyOn(window, "prompt").mockReturnValue("left the company");
  fireEvent.click(screen.getAllByText("vô hiệu hoá")[0]);
  await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && c.url.endsWith("/users/u2"))).toBe(true));
  expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_active: false, reason: "left the company" });
  // reactivate the inactive one
  fireEvent.click(screen.getByText("kích hoạt lại"));
  await waitFor(() => expect(calls.filter((c) => c.method === "PATCH").length).toBe(2));
  expect(calls.filter((c) => c.method === "PATCH")[1].body).toEqual({ is_active: true, reason: "left the company" });
  // role change via the select
  fireEvent.change(screen.getByLabelText("Vai trò op@t"), { target: { value: "REVIEWER" } });
  await waitFor(() => expect(calls.filter((c) => c.method === "PATCH").length).toBe(3));
  expect(calls.filter((c) => c.method === "PATCH")[2].body).toEqual({ role: "REVIEWER", reason: "left the company" });
  // reset password: password prompt then reason prompt
  (window.prompt as unknown as ReturnType<typeof vi.fn>).mockReturnValueOnce("temporary-pass-123").mockReturnValueOnce("forgot it");
  fireEvent.click(screen.getAllByText("đặt lại mật khẩu")[0]);
  await waitFor(() => expect(calls.some((c) => c.url.includes("/reset-password"))).toBe(true));
  expect(calls.find((c) => c.url.includes("/reset-password"))?.body).toEqual({ password: "temporary-pass-123", reason: "forgot it" });
  // create
  fireEvent.click(screen.getByText("Tạo tài khoản"));
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@t" } });
  fireEvent.change(screen.getByLabelText("Họ tên"), { target: { value: "New" } });
  fireEvent.change(screen.getByLabelText("Vai trò"), { target: { value: "REVIEWER" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu ban đầu (≥10 ký tự)"), { target: { value: "initial-pass-1" } });
  fireEvent.click(screen.getByText("Tạo"));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/users"))).toBe(true));
  expect(calls.find((c) => c.method === "POST" && c.url.endsWith("/users"))?.body).toEqual({ email: "new@t", full_name: "New", role: "REVIEWER", password: "initial-pass-1" });
});

test("a reviewer sees the user list read-only", async () => {
  const ro: Ctx = { ...ctx, me: { ...ctx.me, permissions: ["case.read"] }, can: (p) => p === "case.read" };
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/users")) return new Response(JSON.stringify([{ id: "u2", email: "op@t", full_name: "Op", role: "OPERATOR", tenant_id: "t", is_active: true }]), { status: 200 });
    if (url.endsWith("/ready")) return new Response(JSON.stringify({ status: "ready", checks: {} }), { status: 200 });
    return new Response(JSON.stringify({ cases_by_status: {}, open_issues: {}, fields_total: 0, fields_accepted_pct: 0, drafts_exported: 0 }), { status: 200 });
  }) as unknown as typeof fetch;
  render(<Manage ctx={ro} />);
  await waitFor(() => expect(screen.getByText("op@t")).toBeInTheDocument());
  expect(screen.queryByText("Tạo tài khoản")).toBeNull();
  expect(screen.queryByText("vô hiệu hoá")).toBeNull();
  expect(screen.getByText("OPERATOR")).toBeInTheDocument();
});

test("the Audit card shows the tenant-level feed by default and switches to the selected case", async () => {
  const calls: string[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    if (url.includes("/audit?limit=50")) return new Response(JSON.stringify([{ id: "a1", action: "user.deactivated", entity_type: "user", actor_type: "USER", actor_role: "ADMIN", reason: "left the company", created_at: "2026-10-10T01:02:03Z", before: { is_active: true }, after: { is_active: false }, hash: "h" }]), { status: 200 });
    if (url.includes("/cases/c1/audit")) return new Response(JSON.stringify([{ id: "a2", action: "issue.raised", entity_type: "issue", actor_type: "SYSTEM", actor_role: null, reason: null, created_at: "2026-10-10T01:00:00Z", before: null, after: null, hash: "h2" }]), { status: 200 });
    if (url.endsWith("/ready")) return new Response(JSON.stringify({ status: "ready", checks: {} }), { status: 200 });
    if (url.endsWith("/users")) return new Response("[]", { status: 200 });
    return new Response(JSON.stringify({ cases_by_status: {}, open_issues: {}, fields_total: 0, fields_accepted_pct: 0, drafts_exported: 0 }), { status: 200 });
  }) as unknown as typeof fetch;
  render(<Manage ctx={{ ...ctx, caseId: "c1" }} />);
  await waitFor(() => expect(screen.getByText("user.deactivated")).toBeInTheDocument());
  expect(screen.getByText("left the company")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Phạm vi audit"), { target: { value: "case" } });
  await waitFor(() => expect(screen.getByText("issue.raised")).toBeInTheDocument());
  expect(screen.queryByText("user.deactivated")).toBeNull();
  expect(calls.some((c) => c.includes("/cases/c1/audit"))).toBe(true);
});
