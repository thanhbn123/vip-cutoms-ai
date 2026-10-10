import { useEffect, useState } from "react";
import { api, patch, post, type User } from "../api";
import { errMsg, type Ctx } from "../App";
import { Card, Flow, Gap, Metric, ask } from "../components";

interface Summary { cases_by_status: Record<string, number>; open_issues: Record<string, number>; fields_total: number; fields_accepted_pct: number; drafts_exported: number }
interface ProviderHealth { name: string; configured: boolean; healthy: boolean; is_mock: boolean; detail: string }
interface Ready {
  status: string; mode?: string; blocking?: string[];
  checks: Record<string, unknown> & {
    database?: string; migrations?: string; migration_head?: string; migration_in_sync?: boolean; release_sha?: string | null; environment?: string;
    providers?: Record<string, ProviderHealth>;
    customs_data_authoritative?: Record<string, { authoritative?: boolean; version?: string; is_demo?: boolean; reason?: string }> & { all_authoritative?: boolean };
    backup_status?: { state: string; age_hours?: number; destination?: string | null };
  };
}
const CAP: Record<string, string> = { document_ocr: "OCR", document_ai: "Trích xuất", hs_ai: "HS", copilot: "Copilot" };
interface Audit { id: string; action: string; entity_type?: string; actor_type: string; actor_role: string | null; reason: string | null; created_at: string; before: unknown; after: unknown }

export function Manage({ ctx }: { ctx: Ctx }) {
  const [s, setS] = useState<Summary | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [ready, setReady] = useState<Ready | null>(null);
  const [chain, setChain] = useState<boolean | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [auditScope, setAuditScope] = useState<"case" | "tenant">("tenant");  // G18H: tenant feed (accounts, lockouts, knowledge) is the default
  const [err, setErr] = useState<string | null>(null);
  const [newUser, setNewUser] = useState({ email: "", full_name: "", role: "OPERATOR", password: "" });
  const [createOpen, setCreateOpen] = useState(false);
  const loadUsers = () => api<User[]>("/users").then(setUsers).catch(() => undefined);
  const canManage = ctx.can("user.manage");
  // G18G user lifecycle: every change goes through the audited API; failures are shown, never swallowed
  const [auditBump, setAuditBump] = useState(0);
  const run = (p: Promise<unknown>, msg: string) => p.then(() => { setErr(null); ctx.toast(msg); loadUsers(); setAuditBump((b) => b + 1); return true; }).catch((e) => { setErr(errMsg(e)); return false; });
  const createUser = () => run(post("/users", newUser), "Đã tạo tài khoản").then((ok) => { if (ok) { setNewUser({ email: "", full_name: "", role: "OPERATOR", password: "" }); setCreateOpen(false); } });
  const toggleActive = (u: User) => { const r = ask(`Lý do ${u.is_active === false ? "kích hoạt lại" : "vô hiệu hoá"} ${u.email} (≥5 ký tự)`); if (r) run(patch(`/users/${u.id}`, { is_active: u.is_active === false, reason: r }), u.is_active === false ? "Đã kích hoạt lại" : "Đã vô hiệu hoá (token hiện tại hết hiệu lực)"); };
  const changeRole = (u: User, role: string) => { if (role === u.role) return; const r = ask(`Lý do đổi vai trò ${u.email} → ${role} (≥5 ký tự)`); if (r) run(patch(`/users/${u.id}`, { role, reason: r }), "Đã đổi vai trò"); };
  const resetPw = (u: User) => { const pw = window.prompt(`Mật khẩu mới cho ${u.email} (≥10 ký tự) — hãy trao trực tiếp cho người dùng`); if (!pw) return; if (pw.length < 10) { setErr("Mật khẩu phải ≥10 ký tự"); return; } const r = ask("Lý do đặt lại mật khẩu (≥5 ký tự)"); if (r) run(post(`/users/${u.id}/reset-password`, { password: pw, reason: r }), "Đã đặt lại mật khẩu — mọi phiên đăng nhập cũ của người này đã bị huỷ"); };
  useEffect(() => {
    api<Summary>("/dashboard/summary").then(setS).catch((e) => setErr(errMsg(e)));
    loadUsers();
    fetch("/ready").then((r) => r.json()).then(setReady).catch(() => undefined);
    if (!ctx.can("audit.read")) return;
    if (auditScope === "tenant") api<Audit[]>("/audit?limit=50").then(setAudit).catch(() => undefined);
    else if (ctx.caseId) api<Audit[]>(`/cases/${ctx.caseId}/audit`).then((a) => setAudit(a.slice().reverse())).catch(() => undefined);
    else setAudit([]);
  }, [ctx.caseId, ctx.bump, auditScope, auditBump]);
  const total = Object.values(s?.cases_by_status ?? {}).reduce((a, b) => a + b, 0);
  return (
    <>
      <div className="grid g4">
        <Metric label="Cases" value={total} />
        <Metric label="Auto-fill (fields accepted)" value={`${s?.fields_accepted_pct ?? 0}%`} />
        <Metric label="Open critical" value={s?.open_issues?.CRITICAL ?? 0} />
        <Metric label="Release drafts exported" value={s?.drafts_exported ?? 0} />
      </div>
      <Gap />
      <Card title="Production path" right={<span className={`badge ${ready?.status === "ready" ? "ok" : "bad"}`}>{ready?.status ?? "…"}{ready?.mode ? ` · ${ready.mode.toUpperCase()}` : ""}</span>}>
        <Flow steps={["V12 UI accepted", "Backend API", "PostgreSQL", "File storage", "OCR/LLM", "Rule data", "Staging", "Acceptance", "Production"]} on={["V12 UI accepted", "Backend API", "PostgreSQL", "File storage", "Staging", "Acceptance"]} />
        {ready && (
          <div className="grid g2" style={{ marginTop: 8 }} data-testid="readiness">
            <div>
              <p className="mini"><b>Runtime:</b> mode <b>{ready.mode}</b> · env {String(ready.checks.environment ?? "?")} · build {ready.checks.release_sha ? String(ready.checks.release_sha).slice(0, 12) : "n/a"}</p>
              <p className="mini"><b>Database:</b> {String(ready.checks.database ?? "?")} · migration {String(ready.checks.migrations ?? "?")}{ready.checks.migration_in_sync === false ? ` ≠ head ${ready.checks.migration_head}` : " (= head)"}</p>
              <p className="mini"><b>AI providers:</b> {ready.checks.providers ? Object.entries(ready.checks.providers).map(([cap, h]) => `${CAP[cap] ?? cap}: ${h.name}${h.is_mock ? " (mock)" : h.healthy ? " ✓" : " ✗"}`).join(" · ") : "?"}</p>
              <p className="mini"><b>Dữ liệu hải quan:</b> {ready.checks.customs_data_authoritative
                ? (() => {
                  const cds = ready.checks.customs_data_authoritative as Record<string, unknown>;
                  const kinds = Object.entries(cds).filter(([, v]) => typeof v === "object" && v !== null && "authoritative" in (v as object));
                  const note = typeof cds.reason === "string" ? cds.reason : typeof cds.error === "string" ? `lỗi ${cds.error}` : null;
                  return (kinds.length ? kinds.map(([k, v]) => `${k}: ${(v as { authoritative?: boolean }).authoritative ? "authoritative" : "demo/chưa xác minh"}`).join(" · ") : "không đọc được") + (note ? ` (${note})` : "");
                })()
                : "?"}</p>
              <p className="mini"><b>Backup off-host:</b> {ready.checks.backup_status?.state ?? "?"}{ready.checks.backup_status?.age_hours != null ? ` (${ready.checks.backup_status.age_hours} h)` : ""}</p>
            </div>
            <div>
              {ready.blocking?.length
                ? <><p className="mini"><b>Đang chặn readiness ({ready.blocking.length}):</b></p><ul className="mini">{ready.blocking.map((b) => <li key={b}>{b}</li>)}</ul></>
                : <p className="mini">Không có mục nào chặn readiness ở chế độ hiện tại. Chế độ FULL yêu cầu provider thật + dữ liệu authoritative cho cả 4 loại + backup mới (B-01/B-02/B-06).</p>}
            </div>
          </div>
        )}
      </Card>
      <Gap />
      <div className="grid g2">
        <Card title="Roles & users" right={<span className="badge info">{users.length}</span>}>
          {err && <p className="err">{err}</p>}
          <table><thead><tr><th>User</th><th>Role</th>{canManage && <th></th>}</tr></thead><tbody>{users.map((u) => (
            <tr key={u.id} style={u.is_active === false ? { opacity: 0.55 } : undefined}>
              <td>{u.full_name}{u.is_active === false && <span className="badge warn" style={{ marginLeft: 6 }}>inactive</span>}<div className="mini">{u.email}</div></td>
              <td>{canManage && u.id !== ctx.me.user.id
                ? <select aria-label={`Vai trò ${u.email}`} value={u.role} onChange={(e) => changeRole(u, e.target.value)}>{["OPERATOR", "REVIEWER", "SENIOR_REVIEWER", "ADMIN"].map((r) => <option key={r} value={r}>{r}</option>)}</select>
                : u.role}</td>
              {canManage && <td className="mini">{u.id === ctx.me.user.id ? "(bạn)" : <>
                <a href="#" onClick={(e) => { e.preventDefault(); toggleActive(u); }}>{u.is_active === false ? "kích hoạt lại" : "vô hiệu hoá"}</a>
                {" · "}<a href="#" onClick={(e) => { e.preventDefault(); resetPw(u); }}>đặt lại mật khẩu</a>
              </>}</td>}
            </tr>))}</tbody></table>
          {canManage && (
            <div style={{ marginTop: 8 }}>
              <button className="btn secondary small" onClick={() => setCreateOpen((o) => !o)}>{createOpen ? "Đóng" : "Tạo tài khoản"}</button>
              {createOpen && (
                <form onSubmit={(e) => { e.preventDefault(); createUser(); }} style={{ marginTop: 8 }}>
                  <div className="field"><label htmlFor="nu-email">Email</label><input id="nu-email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} required /></div>
                  <div className="field"><label htmlFor="nu-name">Họ tên</label><input id="nu-name" value={newUser.full_name} onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} required /></div>
                  <div className="field"><label htmlFor="nu-role">Vai trò</label><select id="nu-role" value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>{["OPERATOR", "REVIEWER", "SENIOR_REVIEWER", "ADMIN"].map((r) => <option key={r} value={r}>{r}</option>)}</select></div>
                  <div className="field"><label htmlFor="nu-pw">Mật khẩu ban đầu (≥10 ký tự)</label><input id="nu-pw" type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} minLength={10} required autoComplete="new-password" /></div>
                  <button className="btn primary small" type="submit">Tạo</button>
                  <p className="mini">Người dùng nên đổi mật khẩu ngay sau lần đăng nhập đầu (menu "Đổi mật khẩu"). Mọi thay đổi tài khoản đều được audit.</p>
                </form>
              )}
            </div>
          )}
          <p className="mini">Operator: upload, sửa dữ liệu thường, gửi review · Reviewer: duyệt HS/C/O/trị giá/policy · Senior: waive critical, override HS, outcome · Admin: cấu hình, không ra quyết định hải quan.</p>
        </Card>
        <Card title="Audit" right={ctx.can("audit.read") ? <>
            <select aria-label="Phạm vi audit" value={auditScope} onChange={(e) => setAuditScope(e.target.value as "case" | "tenant")}><option value="tenant">Tenant (tài khoản, knowledge, lockout)</option><option value="case">Hồ sơ đang chọn</option></select>{" "}
            <button className="btn secondary small" onClick={() => api<{ chain_valid: boolean }>("/audit/verify").then((r) => setChain(r.chain_valid))}>Verify chain {chain == null ? "" : chain ? "✓" : "✗"}</button></> : undefined}>
          <table><thead><tr><th>Actor</th><th>Action</th><th>Reason</th><th>At</th></tr></thead><tbody>
            {audit.slice(0, 50).map((a) => <tr key={a.id}><td>{a.actor_type}{a.actor_role ? ` · ${a.actor_role}` : ""}</td><td>{a.action}<div className="mini">{a.entity_type}{a.before ? ` · before: ${JSON.stringify(a.before).slice(0, 60)}` : ""}</div></td><td className="mini">{a.reason}</td><td className="mini">{a.created_at.replace("T", " ").slice(0, 19)}</td></tr>)}
            {!audit.length && <tr><td colSpan={4} className="mini">{auditScope === "case" ? "Chọn hồ sơ để xem audit." : "Chưa có sự kiện audit cấp tenant."}</td></tr>}
          </tbody></table>
        </Card>
      </div>
    </>
  );
}
