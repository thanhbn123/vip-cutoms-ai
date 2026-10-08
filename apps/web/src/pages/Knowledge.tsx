import { useEffect, useState } from "react";
import { api, patch, type Dataset } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Callout, Card, Row, ask } from "../components";

interface Rule { heading: string; title: string; keywords: string[]; required_attributes: string[]; base_confidence: number; notes: string | null }
const KIND: Record<string, string> = { HS_RULES: "HS classification", TARIFF: "Tariff (demo rates)", FTA: "C/O & FTA", POLICY: "Policy" };

export function Knowledge({ ctx }: { ctx: Ctx }) {
  const [ds, setDs] = useState<Dataset[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api<Dataset[]>("/knowledge/datasets").then((d) => { setDs(d); const hs = d.find((x) => x.kind === "HS_RULES" && x.is_active); if (hs) api<{ rules: Rule[] }>(`/knowledge/datasets/${hs.id}`).then((r) => setRules(r.rules)); }).catch((e) => setErr(errMsg(e)));
  useEffect(() => { load(); }, [ctx.bump]);
  const toggle = (d: Dataset) => { const r = ask(`Lý do ${d.is_active ? "tắt" : "bật"} ${d.kind} ${d.version}`); if (r) patch(`/knowledge/datasets/${d.id}`, { is_active: !d.is_active, reason: r }).then(() => { ctx.toast("Đã cập nhật dataset"); load(); }).catch((e) => setErr(errMsg(e))); };
  return (
    <div className="grid g2">
      <Card title="Knowledge Hub" right={<span className="badge warn">DEMO — NON-AUTHORITATIVE</span>}>
        {err && <p className="err">{err}</p>}
        <div className="list">
          {ds.map((d) => (<Row key={d.id} title={<>{KIND[d.kind] ?? d.kind} <Badge s={d.is_active ? "PASS" : "REJECTED"}>{d.is_active ? "active" : "inactive"}</Badge> {d.is_demo && <span className="badge warn">demo</span>}</>}>
            v{d.version} · hiệu lực {d.effective_from}{d.effective_to ? ` → ${d.effective_to}` : " → ∞"} · {d.rule_count} rules · nguồn: {d.source}
            {ctx.can("knowledge.manage") && <> · <a href="#" onClick={(e) => { e.preventDefault(); toggle(d); }}>{d.is_active ? "tắt" : "bật"}</a></>}
          </Row>))}
        </div>
        <h3 style={{ fontSize: 12, marginTop: 12 }}>HS heading rules (active dataset)</h3>
        <table><thead><tr><th>Heading</th><th>Title</th><th>Keywords</th><th>Required attrs</th><th>Base</th></tr></thead><tbody>
          {rules.map((r) => <tr key={r.heading}><td>{r.heading}</td><td>{r.title}<div className="mini">{r.notes}</div></td><td>{r.keywords.join(", ")}</td><td>{r.required_attributes.join(", ")}</td><td>{Math.round(r.base_confidence * 100)}%</td></tr>)}
        </tbody></table>
      </Card>
      <Card>
        <Callout kind="pass"><b>Rule:</b> only versioned/current sources may support a decision — mỗi ứng viên HS, thuế, C/O, policy ghi rõ dataset + version + effective date.</Callout>
        <Callout kind="warning"><b>Learning:</b> only reviewer-approved outcomes enter enterprise memory.</Callout>
        <Callout kind="critical"><b>Blocker B-02:</b> dữ liệu pháp lý/biểu thuế thật chưa được owner chọn nguồn. Mọi dataset hiện tại là fixture minh họa, không dùng để khai báo thật.</Callout>
      </Card>
    </div>
  );
}
