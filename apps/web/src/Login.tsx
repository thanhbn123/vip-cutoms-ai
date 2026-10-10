import { useState } from "react";
import { api, ApiError, post, setToken, type Me } from "./api";

export function Login({ onLogin, env }: { onLogin: (me: Me) => void; env: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenant, setTenant] = useState("");
  const [needTenant, setNeedTenant] = useState(false);
  const [tenantOptions, setTenantOptions] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      // The tenant code is optional (G18F): sent only when filled in; the API resolves a unique e-mail by itself.
      const body: Record<string, string> = { email, password };
      if (tenant.trim()) body.tenant = tenant.trim();
      const r = await post<{ access_token: string }>("/auth/login", body);
      setToken(r.access_token);
      onLogin(await api<Me>("/auth/me"));
    } catch (ex) {
      if (ex instanceof ApiError && ex.code === "TENANT_REQUIRED") {
        // The list is only ever returned to the holder of a valid password (G18F): offer it instead of free typing.
        const d = ex.details as { tenants?: unknown } | undefined;
        const opts = Array.isArray(d?.tenants) ? d.tenants.filter((t): t is string => typeof t === "string" && t.length > 0) : [];
        setTenantOptions(opts); setNeedTenant(true); setErr("Email này dùng ở nhiều tenant — chọn tenant để đăng nhập.");
      }
      else setErr(ex instanceof ApiError ? ex.message : "Không kết nối được API");
    } finally { setBusy(false); }
  }
  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="logo" style={{ color: "#172033" }}>VIP Customs AI<small>Đăng nhập · {env}</small></div>
        <div className="field"><label htmlFor="login-email">Email</label><input id="login-email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
        <div className="field"><label htmlFor="login-password">Mật khẩu</label><input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
        {(needTenant || tenant) ? (
          <div className="field"><label htmlFor="login-tenant">Mã tenant</label>
            {tenantOptions.length
              ? <select id="login-tenant" value={tenant} onChange={(e) => setTenant(e.target.value)} required><option value="">— chọn tenant —</option>{tenantOptions.map((t) => <option key={t} value={t}>{t}</option>)}</select>
              : <input id="login-tenant" value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="organization" placeholder="VD: DEMO" required={needTenant} />}
          </div>
        ) : (
          <p className="sub"><a href="#" onClick={(e) => { e.preventDefault(); setNeedTenant(true); }}>Đăng nhập theo mã tenant</a></p>
        )}
        {err && <div className="callout critical">{err}</div>}
        <button className="btn primary" disabled={busy} type="submit">Đăng nhập</button>
        {env === "development" && <p className="sub">Môi trường development: tạo người dùng demo bằng <code>scripts/seed_demo.py</code> (operator / reviewer / senior / admin @demo.local, tenant DEMO).</p>}
      </form>
    </div>
  );
}
