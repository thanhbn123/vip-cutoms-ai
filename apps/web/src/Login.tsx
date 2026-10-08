import { useState } from "react";
import { ApiError, post, setToken, type Me } from "./api";

export function Login({ onLogin, env }: { onLogin: (me: Me) => void; env: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await post<{ access_token: string }>("/auth/login", { email, password });
      setToken(r.access_token);
      const { api } = await import("./api");
      onLogin(await api<Me>("/auth/me"));
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không kết nối được API");
    } finally { setBusy(false); }
  }
  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="logo" style={{ color: "#172033" }}>VIP Customs AI<small>Đăng nhập · {env}</small></div>
        <div className="field"><label htmlFor="login-email">Email</label><input id="login-email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
        <div className="field"><label htmlFor="login-password">Mật khẩu</label><input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
        {err && <div className="callout critical">{err}</div>}
        <button className="btn primary" disabled={busy} type="submit">Đăng nhập</button>
        {env === "development" && <p className="sub">Môi trường development: tạo người dùng demo bằng <code>scripts/seed_demo.py</code> (operator / reviewer / senior / admin @demo.local).</p>}
      </form>
    </div>
  );
}
