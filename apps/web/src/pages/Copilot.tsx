import { useEffect, useRef, useState } from "react";
import { api, post, type Declaration, type Message, type Proposal } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Card, ask } from "../components";

const QUICK = ["Còn thiếu gì để khai?", "Vì sao item 3 chưa chốt được HS?", "Form E có vấn đề gì?", "Trị giá có bất thường không?", "Đề xuất mô tả item 1"];

export function Copilot({ ctx }: { ctx: Ctx }) {
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [props, setProps] = useState<Proposal[]>([]);
  const [d, setD] = useState<Declaration | null>(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const hist = useRef<HTMLDivElement>(null);
  const load = () => { if (!ctx.caseId) return; api<Message[]>(`/cases/${ctx.caseId}/copilot/messages`).then(setMsgs); api<Proposal[]>(`/cases/${ctx.caseId}/proposals`).then(setProps); api<Declaration>(`/cases/${ctx.caseId}/declaration`).then(setD); };
  useEffect(load, [ctx.caseId, ctx.bump]);
  useEffect(() => { hist.current?.scrollTo({ top: hist.current.scrollHeight }); }, [msgs]);
  if (!ctx.caseId) return <Card>Chọn hồ sơ.</Card>;
  const send = async (text: string) => { if (!text.trim()) return; setBusy(true); setErr(null); try { await post(`/cases/${ctx.caseId}/copilot/ask`, { question: text }); setQ(""); load(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); } };
  const decide = async (p: Proposal, decision: "APPROVE" | "REJECT") => { const r = ask("Lý do"); if (!r) return; try { await post(`/cases/${ctx.caseId}/proposals/${p.id}/decide`, { decision, reason: r }); ctx.toast("Đã xử lý đề xuất"); ctx.refresh(); } catch (e) { setErr(errMsg(e)); } };
  return (
    <div className="copilot">
      <div className="card chat">
        <div className="section-title"><h2>AI Copilot</h2><span className="badge purple">Full case context · {msgs[0]?.provider ?? "mock"} provider</span></div>
        <div className="history" ref={hist}>
          <div className="msg ai"><b>VIP Customs AI</b><br />Hồ sơ {d?.case.case_no}: {d?.summary.open_critical ?? 0} critical, {d?.summary.open_warning ?? 0} warning. Hỏi HS, C/O, trị giá hoặc “còn thiếu gì để khai?”.</div>
          {msgs.map((m) => (<div key={m.id} className={`msg ${m.role === "USER" ? "user" : "ai"}`}>{m.role === "AI" && <><b>VIP Customs AI</b> <span className="chip">{m.intent}</span>
            {m.meta?.confidence != null && <span className="chip">confidence {Math.round(m.meta.confidence * 100)}%</span>}
            {m.meta?.requires_review && <Badge s="NEEDS_REVIEW">requires review</Badge>}<br /></>}
            <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
            {m.role === "AI" && (m.meta?.recommended_actions?.length ?? 0) > 0 && <ul className="mini" style={{ margin: "6px 0 0", paddingLeft: 16 }}>{m.meta.recommended_actions!.map((a, i) => <li key={i}>{a}</li>)}</ul>}
            {m.role === "AI" && (m.sources.length > 0 || m.reasoning.length > 0) && <details><summary>Nguồn ({m.sources.length}) · reasoning</summary>
              <div className="mini">{m.sources.map((s, i) => <span key={i} className="chip">{s.type}: {s.label}</span>)}</div><ol className="mini">{m.reasoning.map((r, i) => <li key={i}>{r}</li>)}</ol></details>}
          </div>))}
        </div>
        <div style={{ marginBottom: 6 }}>{QUICK.map((x) => <button key={x} className="btn secondary small" style={{ marginRight: 5, marginBottom: 4 }} disabled={busy} onClick={() => send(x)}>{x}</button>)}</div>
        <textarea id="q" placeholder="Hỏi AI về hồ sơ..." value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(q); } }} />
        <div style={{ marginTop: 7, textAlign: "right" }}>{err && <span className="err" style={{ marginRight: 8 }}>{err}</span>}<button className="btn primary" disabled={busy || !ctx.can("copilot.ask")} onClick={() => send(q)}>Gửi</button></div>
      </div>
      <div>
        <div className="ctx"><h3>Context</h3><p>Case: {d?.case.case_no}</p><p>Items: {d?.summary.items_total}</p><p>Form E: {d?.summary.documents.some((x) => x.doc_type === "CO") ? "Có" : "Không"}</p><p>Readiness: {d?.readiness}%</p></div>
        <div className="ctx"><h3>Guardrails</h3><p>Không tự chốt HS critical.</p><p>Không tự áp dụng FTA khi chưa review.</p><p>Không phát hành khi còn BLOCKED.</p><p>Nguồn do AI trích dẫn được kiểm tra tồn tại trong hồ sơ.</p></div>
        <div className="ctx"><h3>Approval Queue (AI proposals)</h3>
          {props.map((p) => (<div key={p.id} className="row"><strong>Mô tả dòng hàng <Badge s={p.status} /></strong><p>“{p.proposed_value}”</p>
            {p.status === "PROPOSED" && ctx.can("proposal.decide") && <p><button className="btn primary small" onClick={() => decide(p, "APPROVE")}>Duyệt</button> <button className="btn secondary small" onClick={() => decide(p, "REJECT")}>Từ chối</button></p>}</div>))}
          {!props.length && <p>Chưa có đề xuất. Hỏi “đề xuất mô tả item 1”.</p>}
        </div>
      </div>
    </div>
  );
}
