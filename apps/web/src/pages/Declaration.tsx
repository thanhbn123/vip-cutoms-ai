import { useEffect, useState } from "react";
import { api, post, put, type Declaration as Decl, type Field } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Callout, Card, Gap, ask, pct } from "../components";

export function Declaration({ ctx }: { ctx: Ctx }) {
  const [d, setD] = useState<Decl | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (ctx.caseId) api<Decl>(`/cases/${ctx.caseId}/declaration`).then(setD).catch((e) => setErr(errMsg(e))); }, [ctx.caseId, ctx.bump]);
  if (!ctx.caseId) return <Card>Chọn hồ sơ.</Card>;
  if (err) return <Callout kind="critical">{err}</Callout>;
  if (!d) return <Card>Đang tải…</Card>;
  const act = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); ctx.toast(ok); ctx.refresh(); } catch (e) { setErr(errMsg(e)); } };
  const editable = (f: Field) => !f.key.startsWith("case.") && f.key !== "valuation.customs_value";
  const edit = (f: Field) => { const v = window.prompt(`${f.label} — giá trị mới`, f.value ?? ""); if (!v) return; const r = ask("Lý do thay đổi (≥5 ký tự)"); if (r) act(() => put(`/cases/${ctx.caseId}/fields/${f.key}`, { value: v, reason: r }), "Đã lưu trường"); };
  const approve = (f: Field) => { const r = ask("Lý do duyệt", "Đã đối chiếu chứng từ"); if (r) act(() => post(`/cases/${ctx.caseId}/fields/${f.key}/approve`, { value: f.value, reason: r }), "Đã duyệt"); };
  return (
    <>
      <div className="grid g4">
        <div className="card metric"><div className="l">Readiness</div><div className="v">{d.readiness}%</div></div>
        <div className="card metric"><div className="l">Fields OK</div><div className="v">{d.summary.fields_ok}/{d.summary.fields_total}</div></div>
        <div className="card metric"><div className="l">HS approved</div><div className="v">{d.summary.items_hs_approved}/{d.summary.items_total}</div></div>
        <div className="card metric"><div className="l">Open issues</div><div className="v">{d.summary.open_critical + d.summary.open_warning}</div><Badge s={d.summary.open_critical ? "CRITICAL" : "WARNING"}>{d.summary.open_critical} critical</Badge></div>
      </div>
      <Gap />
      {d.sections.map((s) => (
        <div key={s.id}>
          <Card title={s.title} right={s.id === "general" && ctx.can("proposal.decide") ? <button className="btn secondary small" onClick={() => { const r = ask("Lý do duyệt hàng loạt", "Header fields verified against documents"); if (r) act(() => post(`/cases/${ctx.caseId}/fields/approve-all`, { reason: r }), "Đã duyệt các trường không xung đột"); }}>Duyệt tất cả trường critical</button> : <span className="badge info">AI-assisted</span>}>
            <div className="form-grid">
              {s.fields.map((f) => (
                <div key={f.key} className={`field ${["party.importer", "party.exporter", "case.customer", "case.supplier"].includes(f.key) ? "span2" : ""}`}>
                  <label>{f.label} {f.is_critical && <span title="critical">★</span>} <Badge s={f.review_status} /></label>
                  <input readOnly value={f.value ?? ""} placeholder="—" onDoubleClick={() => editable(f) && ctx.can("field.edit") && edit(f)} title={f.reasoning ?? ""} />
                  <div className="mini">{f.source?.source_ref ?? "—"} · {pct(f.confidence)}{f.alternatives?.length ? ` · khác: ${f.alternatives.map((a) => `${a.doc_type}=${a.value}`).join(", ")}` : ""}
                    {editable(f) && ctx.can("field.edit") && <> · <a href="#" onClick={(e) => { e.preventDefault(); edit(f); }}>sửa</a></>}
                    {editable(f) && f.value && f.review_status === "NEEDS_REVIEW" && ctx.can("proposal.decide") && <> · <a href="#" onClick={(e) => { e.preventDefault(); approve(f); }}>duyệt</a></>}
                  </div>
                </div>))}
            </div>
          </Card><Gap />
        </div>))}
      <Card title="Validation" right={<Badge s={d.release_eligible ? "PASS" : "BLOCKED"}>{d.release_eligible ? "release-eligible" : "not eligible"}</Badge>}>
        {d.validation.map((v) => <Callout key={v.code} kind={v.ok ? "pass" : v.severity === "CRITICAL" ? "critical" : "warning"}><b>{v.code}:</b> {v.message}</Callout>)}
      </Card>
    </>
  );
}
