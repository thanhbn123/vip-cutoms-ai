import { useEffect, useState } from "react";
import { api, type User } from "../api";
import { errMsg, type Ctx } from "../App";
import { Card, Flow, Gap, Metric } from "../components";

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
      <Card title="Production path" right={<span className={`badge ${ready?.status === "ready" ? "ok" : "bad"}`}>{ready?.status ?? "…"}{ready?.mode ? ` · ${ready.mode.toUpperCase()}` : ""}</span>}>
        <Flow steps={["V12 UI accepted", "Backend API", "PostgreSQL", "File storage", "OCR/LLM", "Rule data", "Staging", "Acceptance", "Production"]} on={["V12 UI accepted", "Backend API", "PostgreSQL", "File storage", "Staging", "Acceptance"]} />
        {ready && (
          <div className="grid g2" style={{ marginTop: 8 }} data-testid="readiness">
            <div>
              <p className="mini"><b>Runtime:</b> mode <b>{ready.mode}</b> · env {String(ready.checks.environment ?? "?")} · build {ready.checks.release_sha ? String(ready.checks.release_sha).slice(0, 12) : "n/a"}</p>
              <p className="mini"><b>Database:</b> {String(ready.checks.database ?? "?")} · migration {String(ready.checks.migrations ?? "?")}{ready.checks.migration_in_sync === false ? ` ≠ head ${ready.checks.migration_head}` : " (= head)"}</p>
              <p className="mini"><b>AI providers:</b> {ready.checks.providers ? Object.entries(ready.checks.providers).map(([cap, h]) => `${CAP[cap] ?? cap}: ${h.name}${h.is_mock ? " (mock)" : h.healthy ? " ✓" : " ✗"}`).join(" · ") : "?"}</p>
              <p className="mini"><b>Dữ liệu hải quan:</b> {ready.checks.customs_data_authoritative
                ? Object.entries(ready.checks.customs_data_authoritative).filter(([k]) => k !== "all_authoritative").map(([k, v]) => `${k}: ${(v as { authoritative?: boolean }).authoritative ? "authoritative" : "demo/chưa xác minh"}`).join(" · ")
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
