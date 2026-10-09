import { useEffect, useState } from "react";
import { api, post, uploadDocument, type Doc, type Field, type Issue } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Card, Gap, Row, pct } from "../components";

interface Cust { id: string; code: string; name: string }
interface Supp { id: string; name: string; country: string | null }
const DOC_TYPES = ["INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO", "CONTRACT", "CATALOGUE", "OTHER"];
const DOC_LABEL: Record<string, string> = { INVOICE: "Invoice", PACKING_LIST: "Packing List", BILL_OF_LADING: "B/L", CO: "C/O (Form E/D…)", CONTRACT: "Contract", CATALOGUE: "Catalogue", OTHER: "Khác" };

export function CasePage({ ctx }: { ctx: Ctx }) {
  const [customers, setCustomers] = useState<Cust[]>([]);
  const [suppliers, setSuppliers] = useState<Supp[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [fields, setFields] = useState<Field[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [form, setForm] = useState({ customer_id: "", supplier_id: "", declaration_type: "A11", customs_office: "", priority: "NORMAL" });
  const [docType, setDocType] = useState("INVOICE");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newCust, setNewCust] = useState({ code: "", name: "" });
  const [newSupp, setNewSupp] = useState({ name: "", country: "CN" });

  const load = () => {
    api<Cust[]>("/customers").then(setCustomers).catch(() => undefined);
    api<Supp[]>("/suppliers").then(setSuppliers).catch(() => undefined);
    if (ctx.caseId) {
      api<Doc[]>(`/cases/${ctx.caseId}/documents`).then(setDocs).catch(() => undefined);
      api<Field[]>(`/cases/${ctx.caseId}/fields`).then(setFields).catch(() => undefined);
      api<Issue[]>(`/cases/${ctx.caseId}/issues?status=OPEN`).then(setIssues).catch(() => undefined);
    }
  };
  useEffect(load, [ctx.caseId, ctx.bump]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true); setErr(null);
    try { await fn(); ctx.toast(ok); ctx.refresh(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  }
  const createCase = () => run(async () => {
    const c = await post<{ id: string }>("/cases", { ...form, supplier_id: form.supplier_id || null, customs_office: form.customs_office || null });
    await ctx.refreshCases(); ctx.selectCase(c.id);
  }, "Đã tạo hồ sơ");
  const upload = () => file && ctx.caseId && run(() => uploadDocument(ctx.caseId!, docType, file), `Đã tải ${DOC_LABEL[docType]}`);
  const runPipeline = () => ctx.caseId && run(() => post(`/cases/${ctx.caseId}/pipeline/run`), "AI đã parse + map chứng từ");
  const conflictsFor = (d: Doc) => issues.filter((i) => i.category === "DOCUMENT_CONFLICT" && JSON.stringify(i).includes(d.id)).length;

  return (
    <>
      <div className="grid g2">
        <Card title="Tạo hồ sơ hải quan" right={<span className="badge info">{ctx.cases.length} hồ sơ</span>}>
          {!ctx.can("case.create") ? <p className="mini">Vai trò {ctx.me.user.role} không tạo hồ sơ.</p> : (
            <div className="form-grid">
              <div className="field span2"><label>Khách hàng (importer)</label>
                <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}><option value="">— chọn —</option>{customers.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}</select></div>
              <div className="field span2"><label>Nhà cung cấp (exporter)</label>
                <select value={form.supplier_id} onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}><option value="">— không —</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
              <div className="field"><label>Loại hình</label><input value={form.declaration_type} onChange={(e) => setForm({ ...form, declaration_type: e.target.value.toUpperCase() })} /></div>
              <div className="field"><label>Chi cục HQ</label><input value={form.customs_office} onChange={(e) => setForm({ ...form, customs_office: e.target.value })} /></div>
              <div className="field"><label>Ưu tiên</label><select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}><option>LOW</option><option>NORMAL</option><option>HIGH</option></select></div>
              <div className="field" style={{ alignSelf: "end" }}><button className="btn primary" disabled={busy || !form.customer_id} onClick={createCase}>Tạo hồ sơ</button></div>
            </div>)}
          {ctx.can("masterdata.manage") && (
            <details style={{ marginTop: 10 }}><summary>Thêm khách hàng / nhà cung cấp</summary>
              <div className="inline-form" style={{ marginTop: 6 }}>
                <input placeholder="Mã KH" value={newCust.code} onChange={(e) => setNewCust({ ...newCust, code: e.target.value })} />
                <input placeholder="Tên khách hàng" value={newCust.name} onChange={(e) => setNewCust({ ...newCust, name: e.target.value })} />
                <button className="btn secondary small" disabled={!newCust.code || !newCust.name} onClick={() => run(() => post("/customers", newCust), "Đã thêm khách hàng")}>Thêm KH</button>
              </div>
              <div className="inline-form" style={{ marginTop: 6 }}>
                <input placeholder="Tên nhà cung cấp" value={newSupp.name} onChange={(e) => setNewSupp({ ...newSupp, name: e.target.value })} />
                <input placeholder="Quốc gia (CN)" maxLength={2} value={newSupp.country} onChange={(e) => setNewSupp({ ...newSupp, country: e.target.value.toUpperCase() })} />
                <button className="btn secondary small" disabled={!newSupp.name} onClick={() => run(() => post("/suppliers", { ...newSupp, customer_id: form.customer_id || null }), "Đã thêm NCC")}>Thêm NCC</button>
              </div>
            </details>)}
          {err && <p className="err">{err}</p>}
        </Card>
        <Card title="Document Center" right={<span className="badge info">OCR + Parser (mock)</span>}>
          {!ctx.caseId ? <p className="mini">Chọn hoặc tạo hồ sơ.</p> : (<>
            <table><thead><tr><th>Document</th><th>Version</th><th>Parse</th><th>Match</th></tr></thead><tbody>
              {docs.map((d) => (<tr key={d.id}><td>{DOC_LABEL[d.doc_type] ?? d.doc_type}<div className="mini">{d.filename}</div></td><td>v{d.version}</td><td>{pct(d.parse_confidence)}</td>
                <td>{d.status === "PARSE_FAILED" ? <Badge s="PARSE_FAILED">Manual</Badge> : d.status !== "PARSED" ? <Badge s={d.status} /> : conflictsFor(d) ? <Badge s="WARNING">{conflictsFor(d)} issues</Badge> : <Badge s="PASS" />}</td></tr>))}
              {!docs.length && <tr><td colSpan={4} className="mini">Chưa có chứng từ.</td></tr>}
            </tbody></table>
            {ctx.can("document.upload") && (<div className="inline-form" style={{ marginTop: 10 }}>
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>{DOC_TYPES.map((t) => <option key={t} value={t}>{DOC_LABEL[t]}</option>)}</select>
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <button className="btn secondary small" disabled={busy || !file} onClick={upload}>Tải lên</button>
              <button className="btn primary small" disabled={busy || !docs.length} onClick={runPipeline}>Chạy AI (parse + map)</button>
            </div>)}
          </>)}
        </Card>
      </div>
      <Gap />
      <Card title="Data lineage" right={<span className="badge purple">{fields.length} fields</span>}>
        <div className="list">
          {fields.map((f) => (<Row key={f.key} title={<>{f.label} <Badge s={f.review_status} /></>}>{f.source_ref ?? f.source?.source_ref ?? "manual"} → {f.value ?? "—"} · {pct(f.confidence)}{f.alternatives?.length ? ` · conflict with ${f.alternatives.map((a) => a.value).join("/")}` : ""}</Row>))}
          {!fields.length && <p className="mini">Chạy AI để map trường.</p>}
        </div>
      </Card>
    </>
  );
}
