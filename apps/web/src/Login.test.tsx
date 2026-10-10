import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Login } from "./Login";

function mockFetch(calls: { url: string; body: unknown }[], loginResponder: (body: Record<string, string>) => Response) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url, body });
    if (url.includes("/auth/login")) return loginResponder(body);
    if (url.includes("/auth/me")) return new Response(JSON.stringify({ user: { id: "u", email: "a@t", full_name: "A", role: "ADMIN", tenant_id: "t", tenant_code: "T1" }, permissions: [] }), { status: 200 });
    return new Response("{}", { status: 200 });
  }) as unknown as typeof fetch;
}

test("a unique e-mail logs in without a tenant code; the field is not sent when empty", async () => {
  const calls: { url: string; body: unknown }[] = [];
  mockFetch(calls, () => new Response(JSON.stringify({ access_token: "tok", token_type: "bearer" }), { status: 200 }));
  const onLogin = vi.fn();
  render(<Login onLogin={onLogin} env="test" />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "operator@demo.local" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await waitFor(() => expect(onLogin).toHaveBeenCalled());
  const login = calls.find((c) => c.url.includes("/auth/login"));
  expect(login?.body).toEqual({ email: "operator@demo.local", password: "pw" });
});

test("TENANT_REQUIRED reveals the tenant field and the retry sends the code", async () => {
  const calls: { url: string; body: unknown }[] = [];
  mockFetch(calls, (body) => body.tenant
    ? new Response(JSON.stringify({ access_token: "tok", token_type: "bearer" }), { status: 200 })
    : new Response(JSON.stringify({ detail: { code: "TENANT_REQUIRED", message: "this e-mail is used in several tenants; provide the tenant code", details: { tenants: ["T1", "T2"] } } }), { status: 401 }));
  const onLogin = vi.fn();
  render(<Login onLogin={onLogin} env="test" />);
  expect(screen.queryByLabelText("Mã tenant")).toBeNull();
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "shared@both.test" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await waitFor(() => expect(screen.getByLabelText("Mã tenant")).toBeInTheDocument());
  expect(screen.getByText(/nhiều tenant/)).toBeInTheDocument();
  expect(onLogin).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Mã tenant"), { target: { value: "T2" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await waitFor(() => expect(onLogin).toHaveBeenCalled());
  const last = calls.filter((c) => c.url.includes("/auth/login")).pop();
  expect(last?.body).toEqual({ email: "shared@both.test", password: "pw", tenant: "T2" });
});

test("a wrong password shows the generic message and no tenant field", async () => {
  mockFetch([], () => new Response(JSON.stringify({ detail: { code: "INVALID_CREDENTIALS", message: "invalid email, tenant or password" } }), { status: 401 }));
  render(<Login onLogin={vi.fn()} env="test" />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "x@y" } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await waitFor(() => expect(screen.getByText("invalid email, tenant or password")).toBeInTheDocument());
  expect(screen.queryByLabelText("Mã tenant")).toBeNull();
});
