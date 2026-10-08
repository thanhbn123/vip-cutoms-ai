import { useEffect, useState } from "react";
import { api, type Declaration, type Issue, type Item } from "../api";
import { Badge, Callout, Card, Flow, Gap, Metric } from "../components";
import type { Ctx } from "../App";

const STEPS = ["Upload", "Parse", "Map", "Goods", "HS AI", "Tax/C/O", "Policy", "Review", "Draft", "Audit", "Learning"];
const ON: Record<string, string[]> = { NEW: [], DOCUMENTS_UPLOADED: ["Upload"], AI_PROCESSING: ["Parse", "Map", "Goods", "HS AI", "Tax/C/O", "Policy"], REVIEW_REQUIRED: ["Review"], BLOCKED: ["Review"], REVIEWED: ["Review"], READY_TO_EXPORT: ["Draft"], DRAFT_EXPORTED: ["Draft", "Audit", "Learning"] };

export function Home({ ctx }: { ctx: Ctx }) {
  const [d, setD] = useState<Declaration | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!ctx.caseId) return;
    Promise.all([api<Declaration>(`/cases/${ctx.caseId}/declaration`), api<Issue[]>(`/cases/${ctx.caseId}/issues?status=OPEN`), api<Item[]>(`/cases/${ctx.caseId}/items`)])
      .then(([dd, ii, it]) => { setD(dd); setIssues(ii); setItems(it); }).catch((e) => setErr(String(e)));
  }, [ctx.caseId, ctx.bump]);
  if (!ctx.caseId) return <Card title="Chưa có hồ sơ">Tạo hồ sơ đầu tiên trong mục <b>Hồ sơ &amp; chứng từ</b>.</Card>;
  if (err) return <Callout kind="critical">{err}</Callout>;
  if (!d) return <Card>Đang tải…</Card>;
  const crit = issues.filter((i) => i.severity === "CRITICAL");
  const warn = issues.filter((i) => i.severity !== "CRITICAL");
  const hist = items.filter((i) => i.candidates?.[0]?.history_refs?.length).length;
  const okFields = d.sections.flatMap((s) => s.fields).filter((f) => ["APPROVED", "AUTO_ACCEPTABLE", "COMPUTED"].includes(f.review_status) && f.value);
  const reviewFields = d.sections.flatMap((s) => s.fields).filter((f) => f.review_status === "NEEDS_REVIEW");
  return (
    <>
      <div className="grid g4">
        <Metric label="Case readiness" value={`${d.readiness}%`} badge={<Badge s={crit.length ? "CRITICAL" : warn.length ? "WARNING" : "PASS"}>{crit.length ? `${crit.length} critical` : warn.length ? `${warn.length} warning` : "clean"}</Badge>} />
        <Metric label="AI mapped fields" value={d.summary.fields_total} badge={<Badge s="PASS">{d.summary.fields_total ? Math.round((100 * d.summary.fields_ok) / d.summary.fields_total) : 0}%</Badge>} />
        <Metric label="Historical matches" value={hist} badge={<span className="badge purple">Learned</span>} />
        <Metric label="Release" value={d.release_eligible ? "YES" : "NO"} badge={<Badge s={d.release_eligible ? "PASS" : "BLOCKED"}>{d.release_eligible ? d.case.status : "BLOCKED"}</Badge>} />
      </div>
      <Gap />
      <Card title="End-to-end flow" right={<span className="badge info">{d.case.case_no}</span>}><Flow steps={STEPS} on={ON[d.case.status] ?? []} /></Card>
      <Gap />
      <div className="grid g2">
        <Card title="Critical issues">
          {crit.map((i) => <Callout key={i.id} kind="critical"><b>{i.title}</b>{i.detail ? ` — ${i.detail}` : ""}</Callout>)}
          {warn.slice(0, 4).map((i) => <Callout key={i.id} kind="warning"><b>{i.title}</b></Callout>)}
          {!issues.length && <Callout kind="pass"><b>Không còn issue mở.</b></Callout>}
        </Card>
        <Card title="AI summary">
          <Callout kind="pass"><b>Đạt:</b> {okFields.slice(0, 8).map((f) => f.label).join(", ") || "—"}{okFields.length > 8 ? ` +${okFields.length - 8}` : ""}</Callout>
          <Callout kind="warning"><b>Cần duyệt:</b> {reviewFields.slice(0, 6).map((f) => f.label).join(", ") || "—"}; HS: {items.filter((i) => i.hs_status !== "APPROVED").map((i) => `Item ${i.line_no}`).join(", ") || "đã duyệt hết"}</Callout>
          <Callout kind="warning"><b>Lưu ý:</b> {d.disclaimer}</Callout>
        </Card>
      </div>
    </>
  );
}
