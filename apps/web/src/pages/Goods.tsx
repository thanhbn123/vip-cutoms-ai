import { useEffect, useState } from "react";
import { api, patch, post, type Assessment, type Item } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Card, ask, pct } from "../components";

export function Goods({ ctx }: { ctx: Ctx }) {
  const [items, setItems] = useState<Item[]>([]);
  const [assess, setAssess] = useState<Assessment[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  useEffect(() => {
    if (!ctx.caseId) return;
    api<Item[]>(`/cases/${ctx.caseId}/items`).then(setItems).catch((e) => setErr(errMsg(e)));
    api<Assessment[]>(`/cases/${ctx.caseId}/assessments`).then(setAssess).catch(() => undefined);
  }, [ctx.caseId, ctx.bump]);
  if (!ctx.caseId) return <Card>Chọn hồ sơ.</Card>;
  const act = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); ctx.toast(ok); ctx.refresh(); } catch (e) { setErr(errMsg(e)); } };
  const a = (it: Item, kind: string) => assess.find((x) => x.item_id === it.id && x.kind === kind);
  const decide = (it: Item, decision: "APPROVE" | "REJECT", cand?: string) => {
    const r = ask(decision === "APPROVE" ? `Lý do duyệt HS ${code} (≥5 ký tự)` : "Lý do từ chối ứng viên");
    if (r) act(() => post(`/cases/${ctx.caseId}/items/${it.id}/hs-decision`, { decision, hs_code: decision === "APPROVE" ? code : undefined, candidate_id: cand, reason: r, evidence: [] }), decision === "APPROVE" ? "HS đã duyệt" : "Đã từ chối ứng viên");
  };
  const addAttr = (it: Item) => { const k = window.prompt("Thuộc tính (function / voltage / power / application / material)"); const v = k && window.prompt(`Giá trị cho ${k}`); const r = v && ask("Nguồn/lý do (≥5 ký tự)"); if (k && v && r) act(() => patch(`/cases/${ctx.caseId}/items/${it.id}`, { attributes: { [k]: v }, reason: r }), "Đã cập nhật thuộc tính"); };
  const editDesc = (it: Item) => { const v = window.prompt("Mô tả khai báo (VN)", it.description_vn ?? ""); const r = v && ask("Lý do"); if (v && r) act(() => patch(`/cases/${ctx.caseId}/items/${it.id}`, { description_vn: v, reason: r }), "Đã lưu mô tả"); };
  const coDecide = (it: Item, decision: "APPLY" | "DO_NOT_APPLY") => { const r = ask("Lý do quyết định C/O"); if (r) act(() => post(`/cases/${ctx.caseId}/items/${it.id}/co-decision`, { decision, reason: r }), "Đã ghi quyết định C/O"); };
  return (
    <Card title="Goods & HS AI" right={<span className="badge purple">Reason + confidence · demo rules</span>}>
      {err && <p className="err">{err}</p>}
      <table><thead><tr><th>#</th><th>Goods</th><th>HS candidate</th><th>History</th><th>Confidence</th><th>Status</th></tr></thead><tbody>
        {items.map((it) => { const top = it.candidates[0]; const hist = top?.history_refs ?? []; return (
          <tr key={it.id} onClick={() => setOpen(open === it.id ? null : it.id)} style={{ cursor: "pointer" }}>
            <td>{it.line_no}</td>
            <td>{it.description_vn ?? it.description}<div className="mini">{it.model} · {it.quantity} {it.unit} · {it.unit_price}</div></td>
            <td>{it.hs_code ?? (top ? `${top.heading}.xx.xx` : "—")}<div className="mini">{top?.title}</div></td>
            <td>{hist.length ? (hist.some((h) => !h.reusable) ? `Prior ${hist.find((h) => !h.reusable)?.outcome.toLowerCase()}` : `${hist.length} approved match${hist.length > 1 ? "es" : ""}`) : (top && top.confidence >= 0.9 ? "Stable" : "—")}</td>
            <td>{pct(it.hs_confidence)}</td>
            <td><Badge s={it.hs_status}>{it.hs_status === "NEEDS_REVIEW" ? "REVIEW" : it.hs_status === "APPROVED" ? "APPROVED" : it.hs_status}</Badge></td>
          </tr>); })}
        {!items.length && <tr><td colSpan={6} className="mini">Chưa có dòng hàng — chạy AI ở Document Center.</td></tr>}
      </tbody></table>
      {items.filter((it) => it.id === open).map((it) => (
        <div key={it.id} className="card" style={{ marginTop: 10 }}>
          <div className="section-title"><h2>Item {it.line_no} — {it.model ?? it.description}</h2><Badge s={it.hs_status} /></div>
          <div className="grid g2">
            <div>
              <h3 style={{ fontSize: 12 }}>Ứng viên HS</h3>
              {it.candidates.map((c) => (<div key={c.id} className="row"><strong>{c.heading} — {c.title} · {pct(c.confidence)} <Badge s={c.status} /></strong>
                <p>{c.reasoning.join(" ")}</p>{c.missing_attributes.length > 0 && <p><b>Thiếu:</b> {c.missing_attributes.join(", ")}</p>}
                <p className="mini">dataset {c.dataset_version} · {c.history_refs.map((h) => `${h.case_no}: ${h.hs_code} (${h.match}${h.reusable ? "" : ", do not auto-copy"})`).join("; ")}</p>
                {ctx.can("hs.decide") && it.hs_status !== "APPROVED" && <button className="btn secondary small" onClick={() => decide(it, "REJECT", c.id)}>Từ chối ứng viên</button>}
              </div>))}
              {ctx.can("hs.decide") && it.hs_status !== "APPROVED" && (<div className="inline-form" style={{ marginTop: 8 }}>
                <input placeholder="HS 8 số" maxLength={8} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
                <button className="btn primary small" disabled={code.length !== 8} onClick={() => decide(it, "APPROVE", it.candidates.find((c) => c.heading === code.slice(0, 4))?.id)}>Duyệt HS</button>
                <span className="mini">Mã ngoài ứng viên AI cần Senior Reviewer + evidence.</span></div>)}
            </div>
            <div>
              <h3 style={{ fontSize: 12 }}>Thuộc tính kỹ thuật & nguồn</h3>
              <div className="kv">{Object.entries(it.attributes ?? {}).map(([k, v]) => (<><b key={k + "k"}>{k}</b><span key={k + "v"}>{v.value} <span className="chip">{v.source}</span></span></>))}
                <b>source</b><span>{it.source_ref}</span><b>C/O line</b><span>{it.co_line_matched == null ? "không có trên C/O" : it.co_line_matched ? "khớp" : "KHÔNG khớp"} · {it.origin_criterion ?? "—"}</span></div>
              {ctx.can("field.edit") && <div className="inline-form" style={{ marginTop: 8 }}><button className="btn secondary small" onClick={() => addAttr(it)}>+ Thuộc tính</button><button className="btn secondary small" onClick={() => editDesc(it)}>Sửa mô tả VN</button></div>}
              <h3 style={{ fontSize: 12, marginTop: 10 }}>Tax / C/O / Policy (demo datasets)</h3>
              {["CO", "TAX", "POLICY"].map((k) => { const x = a(it, k); return x ? (<div key={k} className="row"><strong>{k} <Badge s={x.status} /> {x.dataset_is_demo && <span className="badge warn">DEMO DATA · NOT FOR CUSTOMS FILING</span>}</strong><p>{x.reasoning.join(" ")} {k === "TAX" && x.result.total_tax ? `→ thuế ${String(x.result.import_duty)} + VAT ${String(x.result.vat)}` : ""}</p>
                {k === "CO" && ctx.can("proposal.decide") && !x.reviewer_decision && x.status !== "NOT_COVERED" && <p><button className="btn secondary small" disabled={x.status !== "ELIGIBLE_PENDING_REVIEW"} onClick={() => coDecide(it, "APPLY")}>Áp dụng C/O</button> <button className="btn secondary small" onClick={() => coDecide(it, "DO_NOT_APPLY")}>Không áp dụng</button></p>}
                {k === "CO" && x.reviewer_decision && <p className="mini">Reviewer: {x.reviewer_decision.decision}</p>}</div>) : null; })}
            </div>
          </div>
        </div>))}
    </Card>
  );
}
