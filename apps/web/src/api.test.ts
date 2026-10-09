import { api, ApiError } from "./api";

afterEach(() => { vi.restoreAllMocks(); });

test("a non-JSON upstream error (proxy 502 HTML) becomes an ApiError, not a SyntaxError", async () => {
  globalThis.fetch = vi.fn(async () => new Response("<html><body>502 Bad Gateway</body></html>", { status: 502, headers: { "Content-Type": "text/html" } })) as unknown as typeof fetch;
  await expect(api("/cases")).rejects.toMatchObject({ status: 502, code: "UPSTREAM" } satisfies Partial<ApiError>);
});

test("a JSON error keeps its machine-readable code", async () => {
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ detail: { code: "FORBIDDEN", message: "no" } }), { status: 403, headers: { "Content-Type": "application/json" } })) as unknown as typeof fetch;
  await expect(api("/cases")).rejects.toMatchObject({ status: 403, code: "FORBIDDEN", message: "no" });
});
