import { render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { NAV } from "./nav";

function mockFetch(routes: Record<string, unknown>) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(routes).find((k) => url.includes(k));
    if (!key) return new Response(JSON.stringify({ detail: { code: "NOT_FOUND", message: url } }), { status: 404 });
    return new Response(JSON.stringify(routes[key]), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
}

beforeEach(() => { localStorage.clear(); });

test("without a token the login screen is shown", async () => {
  mockFetch({ "/ready": { status: "ready", checks: { environment: "test" } } });
  render(<App />);
  await waitFor(() => expect(screen.getByText("Đăng nhập", { selector: "button" })).toBeInTheDocument());
});

test("with a token the nine V12 sidebar entries render in order", async () => {
  localStorage.setItem("vip.token", "x.y");
  mockFetch({
    "/ready": { status: "ready", checks: { environment: "test" } },
    "/auth/me": { user: { id: "u", email: "r@t", full_name: "R", role: "REVIEWER", tenant_id: "t" }, permissions: ["case.read"] },
    "/knowledge/notice": { demo_active: true, notice: "DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING", datasets: ["HS_RULES demo-hs-2026.10"], non_demo_datasets: [] },
    "/cases": [],
  });
  render(<App />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Hồ sơ & chứng từ" })).toBeInTheDocument());
  await waitFor(() => expect(screen.getByRole("note")).toHaveTextContent("NOT FOR CUSTOMS FILING"));
  const labels = screen.getAllByRole("button", { name: /.+/ }).map((b) => b.textContent).filter((t) => NAV.some((n) => n.label === t));
  expect(labels).toEqual(NAV.map((n) => n.label));
});
