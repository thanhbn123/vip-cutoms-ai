import { useEffect, useState } from "react";
import { api, getToken, post, type Draft, type Issue, type QueueRow } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Callout, Card, Gap, Row, ask } from "../components";

interface Gate { eligible: boolean; checks: { code: string; ok: boolean; severity: string; message: string }[]; status: string }

export function Review({ ctx }: { ctx: Ctx }) {
  const [queue, setQueue] = useState<QueueRow[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [gate, setGate] = useState<Gate | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = () => { api<QueueRow[]>("/review/queue").then(setQueue).catch(() => undefined); if (ctx.caseId) { api<Issue[]>(`/cases/${ctx.caseId}/issues?status=OPEN`).then(setIssues); api<Gate>(`/cases/${ctx.caseId}/release-gate`).then(setGate); api<Draft[]>(`/cases/${ctx.caseId}/drafts`).then(setDrafts); } };
  useEffect(load, [ctx.caseId, ctx.bump]);
  const act = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); ctx.toast(ok); ctx.refresh(); } catch (e) { setErr(errMsg(e)); } };
  const resolve = (i: Issue) => { const r = ask("Lý do resolve (≥5 ký tự)"); if (r) act(() => post(`/cases/${ctx.caseId}/issues/${i.id}/resolve`, { reason: r }), "Đã resolve"); };
  const waive = (i: Issue) => { const r = ask("Lý do waive (≥5 ký tự)"); const ev = r && i.severity === "CRITICAL" ? window.prompt("Evidence ref (bắt buộc với critical)") : ""; if (r) act(() => post(`/cases/${ctx.caseId}/issues/${i.id}/waive`, { reason: r, evidence: ev ? [ev] : [] }), "Đã waive"); };
  const download = async (d: Draft, fmt: "json" | "csv") => { const res = await fetch(`/api/v1/drafts/${d.id}?format=${fmt}`, { headers: { Authorization: `Bearer ${getToken()}` } }); const blob = await res.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `draft-v${d.version}.${fmt}`; a.click(); };
  return (
    <>
      <div className="grid g2">
        <Card title="Reviewer Queue" right={<Badge s="WARNING">{queue.length} open</Badge>}>
          <div className="list">
            {queue.map((r) => (<Row key={r.case_id} title={<a href="#" onClick={(e) => { e.preventDefault(); ctx.selectCase(r.case_id); }}>{r.case_no} <Badge s={r.status} /> {r.priority === "HIGH" && <span className="badge bad">HIGH</span>}</a>}>
              {r.open_critical} critical · {r.open_warning} warning · {r.top_issues.map((i) => i.title).join(" · ")}</Row>))}
            {!queue.length && <p className="mini">Queue trống.</p>}
          </div>
          <Gap />
          <h3 style={{ fontSize: 12 }}>Issues hồ sơ hiện tại</h3>
          <div className="list">
            {issues.map((i) => (<Row key={i.id} title={<>{i.title} <Badge s={i.severity} /></>}>{i.category} · {i.target_ref ?? "case"} · {i.assignee_role}{i.detail ? ` · ${i.detail}` : ""}
              {ctx.can("issue.resolve") && <> · <a href="#" onClick={(e) => { e.preventDefault(); resolve(i); }}>resolve</a></>}
              {(i.severity === "CRITICAL" ? ctx.can("issue.waive_critical") : ctx.can("issue.waive_warning")) && <> · <a href="#" onClick={(e) => { e.preventDefault(); waive(i); }}>waive</a></>}</Row>))}
            {!issues.length && ctx.caseId && <Callout kind="pass"><b>Không còn issue mở.</b></Callout>}
          </div>
        </Card>
        <Card title="Release Gate" right={<Badge s={gate?.eligible ? "PASS" : "BLOCKED"}>{gate?.eligible ? "ELIGIBLE" : "BLOCKED"}</Badge>}>
          {err && <p className="err">{err}</p>}
          {gate?.checks.map((c) => <Callout key={c.code} kind={c.ok ? "pass" : c.severity === "CRITICAL" ? "critical" : "warning"}><b>{c.ok ? "Đạt" : "Chưa đạt"}:</b> {c.message}</Callout>)}
          <Callout kind="pass"><b>Cho phép:</b> xuất bản nháp nội bộ có watermark DRAFT ở mọi trạng thái.</Callout>
          <div style={{ marginTop: 10 }} className="inline-form">
            <button className="btn secondary" disabled={!ctx.caseId} onClick={() => act(() => post(`/cases/${ctx.caseId}/drafts`, { kind: "PREVIEW", reason: "internal preview" }), "Đã xuất DRAFT nội bộ")}>Xuất DRAFT</button>
            <button className="btn dark" disabled={!gate?.eligible || !ctx.can("case.mark_ready") || gate?.status !== "REVIEWED"} onClick={() => { const r = ask("Lý do đánh dấu READY", "All release checks passed"); if (r) act(() => post(`/cases/${ctx.caseId}/mark-ready`, { reason: r }), "READY_TO_EXPORT"); }}>Đánh dấu READY</button>
            <button className="btn primary" disabled={!gate?.eligible || !ctx.can("draft.export_release") || !["READY_TO_EXPORT", "DRAFT_EXPORTED"].includes(gate?.status ?? "")} onClick={() => act(() => post(`/cases/${ctx.caseId}/drafts`, { kind: "RELEASE", reason: "release draft" }), "Đã xuất bản nháp phát hành (internal)")}>Phát hành bản nháp</button>
          </div>
          <p className="mini">Không có kết nối VNACCS/ECUS. “Phát hành” chỉ tạo bản nháp nội bộ có phiên bản, checksum và audit.</p>
          <Gap />
          <h3 style={{ fontSize: 12 }}>Drafts</h3>
          <div className="list">{drafts.map((d) => (<Row key={d.id} title={<>v{d.version} · {d.kind} <Badge s={d.release_eligible ? "PASS" : "WARNING"}>{d.release_eligible ? "release-eligible" : "preview"}</Badge></>}>{d.watermark} · {d.checksum.slice(0, 12)}… · <a href="#" onClick={(e) => { e.preventDefault(); download(d, "json"); }}>JSON</a> · <a href="#" onClick={(e) => { e.preventDefault(); download(d, "csv"); }}>CSV</a></Row>))}</div>
        </Card>
      </div>
    </>
  );
}
