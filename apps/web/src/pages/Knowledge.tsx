import { useEffect, useState } from "react";
import { api, patch, post, type Dataset, type DemoNotice } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Callout, Card, Row, ask } from "../components";

interface Rule { heading: string; title: string; keywords: string[]; required_attributes: string[]; base_confidence: number; notes: string | null }
interface DatasetDetail extends Dataset { provenance_problems?: string[]; rules?: Rule[]; payload?: unknown }
const KIND: Record<string, string> = { HS_RULES: "HS classification", TARIFF: "Tariff", FTA: "C/O & FTA", POLICY: "Policy" };
const PROBLEM: Record<string, string> = {
  source_authority: "thiếu cơ quan ban hành", source_document: "thiếu văn bản pháp lý", source_reference: "thiếu tham chiếu/URL",
  effective_from: "thiếu ngày hiệu lực", version: "thiếu version", is_demo: "dữ liệu demo — không thể xác minh", checksum: "thiếu checksum",
  checksum_mismatch: "checksum không khớp (payload đã bị sửa sau khi import)",
};

const IMPORT_TEMPLATE = JSON.stringify({
  kind: "TARIFF", version: "mfn-2026-01", label: "Biểu thuế nhập khẩu (MFN) 2026", effective_from: "2026-01-01", effective_to: null,
  source_authority: "<cơ quan ban hành>", source_document: "<số/tên văn bản>", source_reference: "<URL hoặc mã lưu trữ>",
  payload: { rates: { "84131100": { mfn_duty_pct: 0, vat_pct: 10 } } }, reason: "<lý do import — được ghi audit>",
}, null, 2);

export function Knowledge({ ctx }: { ctx: Ctx }) {
  const [ds, setDs] = useState<Dataset[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [notice, setNotice] = useState<DemoNotice | null>(null);
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState(IMPORT_TEMPLATE);
  const load = () => {
    api<Dataset[]>("/knowledge/datasets").then((d) => { setDs(d); const hs = d.find((x) => x.kind === "HS_RULES" && x.is_active && !x.superseded_at); if (hs) api<{ rules: Rule[] }>(`/knowledge/datasets/${hs.id}`).then((r) => setRules(r.rules)); }).catch((e) => setErr(errMsg(e)));
    api<DemoNotice>("/knowledge/notice").then(setNotice).catch(() => setNotice(null));
  };
  useEffect(() => { load(); }, [ctx.bump]);
  // resolves true on success, false on failure (the error is shown; callers must not treat a failure as done)
  const run = (p: Promise<unknown>, msg: string) => p.then(() => { setErr(null); ctx.toast(msg); setDetail(null); load(); return true; }).catch((e) => { setErr(errMsg(e)); return false; });
  const toggle = (d: Dataset) => { const r = ask(`Lý do ${d.is_active ? "tắt" : "bật"} ${d.kind} ${d.version}`); if (r) run(patch(`/knowledge/datasets/${d.id}`, { is_active: !d.is_active, reason: r }), "Đã cập nhật dataset"); };
  const verify = (d: Dataset) => { const r = ask(`Xác minh ${d.kind} ${d.version} theo văn bản nào? (lý do, ≥5 ký tự)`); if (r) run(post(`/knowledge/datasets/${d.id}/verify`, { reason: r }), "Đã xác minh: dataset là AUTHORITATIVE"); else setErr("Cần lý do ≥5 ký tự"); };
  const supersede = (d: Dataset) => {
    const candidates = ds.filter((x) => x.kind === d.kind && x.id !== d.id && !x.superseded_at);
    if (!candidates.length) { setErr("Không có dataset cùng loại để thay thế"); return; }
    const pick = window.prompt(`Dataset thay thế (version): ${candidates.map((c) => c.version).join(" | ")}`, candidates[0].version);
    const target = candidates.find((c) => c.version === (pick ?? "").trim());
    if (!target) { if (pick !== null) setErr(`Không có dataset version "${pick}" cùng loại`); return; }
    const r = ask(`Lý do thay thế ${d.version} bằng ${target.version}`); if (r) run(post(`/knowledge/datasets/${d.id}/supersede`, { new_dataset_id: target.id, reason: r }), "Đã ghi nhận thay thế (lineage giữ nguyên)");
  };
  const open = (d: Dataset) => api<DatasetDetail>(`/knowledge/datasets/${d.id}`).then(setDetail).catch((e) => setErr(errMsg(e)));
  const doImport = () => {
    let body: unknown;
    try { body = JSON.parse(importText); } catch { setErr("Gói dữ liệu không phải JSON hợp lệ"); return; }
    run(post("/knowledge/datasets/import", body), "Đã import (INACTIVE, chưa xác minh)").then((ok) => { if (ok) setImportOpen(false); });
  };
  const canManage = ctx.can("knowledge.manage"), canVerify = ctx.can("knowledge.verify");
  const authoritative = ds.filter((d) => d.is_authoritative && d.is_active && !d.superseded_at).length;
  // Fail closed (G18E): the warning stays unless the notice endpoint positively reports no demo data in use.
  const demoWarning = notice ? notice.demo_active : ds.some((d) => d.is_demo && d.is_active && !d.superseded_at) || true;
  return (
    <div className="grid g2">
      <Card title="Knowledge Hub" right={demoWarning
        ? <span className="badge warn">DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING</span>
        : <span className="badge pass">{authoritative} authoritative dataset(s) active</span>}>
        {err && <p className="err">{err}</p>}
        {notice && <p className="mini">Chế độ: <b>{notice.app_mode ?? "?"}</b>{notice.authoritative_datasets?.length ? ` · authoritative: ${notice.authoritative_datasets.join(", ")}` : " · chưa có dataset authoritative nào đang bật"}</p>}
        <div className="list">
          {ds.map((d) => (<Row key={d.id} title={<>{KIND[d.kind] ?? d.kind} <Badge s={d.superseded_at ? "REJECTED" : d.is_active ? "PASS" : "REJECTED"}>{d.superseded_at ? "superseded" : d.is_active ? "active" : "inactive"}</Badge>
              {d.is_demo && <span className="badge warn">demo</span>}
              {d.is_authoritative ? <span className="badge pass">authoritative</span> : !d.is_demo && <span className="badge warn">chưa xác minh</span>}</>}>
            v{d.version} · hiệu lực {d.effective_from}{d.effective_to ? ` → ${d.effective_to}` : " → ∞"} · {d.rule_count} rules
            <span className="mini" style={{ display: "block" }}>nguồn: {d.source_authority ? `${d.source_authority} · ${d.source_document ?? "?"} · ${d.source_reference ?? "?"}` : d.source}
              {d.verified_at && ` · xác minh ${d.verified_at.slice(0, 10)}`}{d.checksum && ` · sha256 ${d.checksum.slice(0, 12)}`}{d.supersedes_id && " · thay thế bản trước"}</span>
            <a href="#" onClick={(e) => { e.preventDefault(); open(d); }}>chi tiết</a>
            {canManage && <> · <a href="#" onClick={(e) => { e.preventDefault(); toggle(d); }}>{d.is_active ? "tắt" : "bật"}</a></>}
            {canVerify && !d.is_authoritative && !d.is_demo && <> · <a href="#" onClick={(e) => { e.preventDefault(); verify(d); }}>xác minh</a></>}
            {canManage && !d.superseded_at && <> · <a href="#" onClick={(e) => { e.preventDefault(); supersede(d); }}>thay thế</a></>}
          </Row>))}
        </div>
        {canManage && (
          <div style={{ marginTop: 12 }}>
            <button className="btn" onClick={() => setImportOpen((o) => !o)}>{importOpen ? "Đóng" : "Import gói dữ liệu (JSON)"}</button>
            {importOpen && (<div style={{ marginTop: 8 }}>
              <p className="mini">Gói được lưu ở trạng thái INACTIVE và CHƯA XÁC MINH. Một ADMIN/Senior xác minh theo văn bản pháp lý rồi mới bật. Xem docs/G18_CUSTOMS_DATA_SCHEMA.md.</p>
              <textarea aria-label="Gói dữ liệu JSON" value={importText} onChange={(e) => setImportText(e.target.value)} rows={14} style={{ width: "100%", fontFamily: "monospace", fontSize: 11 }} />
              <button className="btn primary" onClick={doImport}>Import</button>
            </div>)}
          </div>
        )}
        {detail && (<Card title={`${KIND[detail.kind] ?? detail.kind} ${detail.version}`} right={<a href="#" onClick={(e) => { e.preventDefault(); setDetail(null); }}>đóng</a>}>
          {detail.provenance_problems?.length
            ? <Callout kind="warning"><b>Chưa đủ điều kiện xác minh:</b> {detail.provenance_problems.map((p) => PROBLEM[p] ?? p).join("; ")}</Callout>
            : <Callout kind="pass"><b>Đủ nguồn pháp lý:</b> {detail.source_authority} · {detail.source_document} · {detail.source_reference}</Callout>}
          <pre className="mini" style={{ maxHeight: 240, overflow: "auto" }}>{JSON.stringify(detail.rules ?? detail.payload, null, 2)}</pre>
        </Card>)}
        <h3 style={{ fontSize: 12, marginTop: 12 }}>HS heading rules (active dataset)</h3>
        <table><thead><tr><th>Heading</th><th>Title</th><th>Keywords</th><th>Required attrs</th><th>Base</th></tr></thead><tbody>
          {rules.map((r) => <tr key={r.heading}><td>{r.heading}</td><td>{r.title}<div className="mini">{r.notes}</div></td><td>{r.keywords.join(", ")}</td><td>{r.required_attributes.join(", ")}</td><td>{Math.round(r.base_confidence * 100)}%</td></tr>)}
        </tbody></table>
      </Card>
      <Card>
        <Callout kind="pass"><b>Rule:</b> only versioned/current sources may support a decision — mỗi ứng viên HS, thuế, C/O, policy ghi rõ dataset + version + effective date.</Callout>
        <Callout kind="warning"><b>Quy trình:</b> import (INACTIVE) → xác minh theo văn bản (ADMIN/Senior) → bật → thay thế bản cũ. Hai dataset authoritative cùng hiệu lực sẽ chặn hồ sơ cho đến khi reviewer giải quyết.</Callout>
        <Callout kind="warning"><b>Learning:</b> only reviewer-approved outcomes enter enterprise memory.</Callout>
        <Callout kind="critical"><b>Blocker B-02:</b> dữ liệu pháp lý/biểu thuế thật chưa được owner chọn nguồn. Mọi dataset demo là fixture minh họa, không dùng để khai báo thật.</Callout>
      </Card>
    </div>
  );
}
