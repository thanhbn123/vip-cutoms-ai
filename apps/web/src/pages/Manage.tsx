import { useEffect, useState } from "react";
import { api, type User } from "../api";
import { errMsg, type Ctx } from "../App";
import { Card, Flow, Gap, Metric } from "../components";

interface Summary { cases_by_status: Record<string, number>; open_issues: Record<string, number>; fields_total: number; fields_accepted_pct: number; drafts_exported: number }
interface Ready { status: string; checks: Record<string, string> }
interface Audit { id: string; action: string; actor_type: string; actor_role: string | null; reason: string | null; created_at: string; before: unknown; after: unknown }

export function Manage({ ctx }: { ctx: Ctx }) {
  const [s, setS] = useState<Summary | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [ready, setReady] = useState<Ready | null>(null);
  const [chain, setChain] = useState<boolean | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<Summary>("/dashboard/summary").then(setS).catch((e) => setErr(errMsg(e)));
    api<User[]>("/users").then(setUsers).catch(() => undefined);
    fetch("/ready").then((r) => r.json()).then(setReady).catch(() => undefined);
    if (ctx.caseId && ctx.can("audit.read")) api<Audit[]>(`/cases/${ctx.caseId}/audit`).then((a) => setAudit(a.slice().reverse())).catch(() => undefined);
  }, [ctx.caseId, ctx.bump]);
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
      <Card title="Production path" right={<span className={`badge ${ready?.status === "ready" ? "ok" : "bad"}`}>{ready?.status ?? "…"}</span>}>
        <Flow steps={["V12 UI accepted", "Backend API", "PostgreSQL", "File storage", "OCR/LLM", "Rule data", "Staging", "Acceptance", "Production"]} on={["V12 UI accepted", "Backend API", "PostgreSQL", "File storage"]} />
        <p className="mini">API checks: {ready ? Object.entries(ready.checks).map(([k, v]) => `${k}=${v}`).join(" · ") : "…"} · OCR/LLM = mock provider · Rule data = demo fixtures · Staging/Production = chưa (BLOCKED_OWNER).</p>
      </Card>
      <Gap />
      <div className="grid g2">
        <Card title="Roles & users" right={<span className="badge info">{users.length}</span>}>
          {err && <p className="err">{err}</p>}
          <table><thead><tr><th>User</th><th>Role</th></tr></thead><tbody>{users.map((u) => <tr key={u.id}><td>{u.full_name}<div className="mini">{u.email}</div></td><td>{u.role}</td></tr>)}</tbody></table>
          <p className="mini">Operator: upload, sửa dữ liệu thường, gửi review · Reviewer: duyệt HS/C/O/trị giá/policy · Senior: waive critical, override HS, outcome · Admin: cấu hình, không ra quyết định hải quan.</p>
        </Card>
        <Card title="Audit" right={ctx.can("audit.read") ? <button className="btn secondary small" onClick={() => api<{ chain_valid: boolean }>("/audit/verify").then((r) => setChain(r.chain_valid))}>Verify chain {chain == null ? "" : chain ? "✓" : "✗"}</button> : undefined}>
          <table><thead><tr><th>Actor</th><th>Action</th><th>Reason</th><th>At</th></tr></thead><tbody>
            {audit.slice(0, 25).map((a) => <tr key={a.id}><td>{a.actor_type}{a.actor_role ? ` · ${a.actor_role}` : ""}</td><td>{a.action}<div className="mini">{a.before ? `before: ${JSON.stringify(a.before).slice(0, 60)}` : ""}</div></td><td className="mini">{a.reason}</td><td className="mini">{a.created_at.replace("T", " ").slice(0, 19)}</td></tr>)}
            {!audit.length && <tr><td colSpan={4} className="mini">Chọn hồ sơ để xem audit.</td></tr>}
          </tbody></table>
        </Card>
      </div>
    </>
  );
}
