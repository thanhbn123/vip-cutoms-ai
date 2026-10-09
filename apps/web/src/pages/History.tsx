import { useEffect, useState } from "react";
import { api, post, type Memory } from "../api";
import { errMsg, type Ctx } from "../App";
import { Badge, Card, ask } from "../components";

export function History({ ctx }: { ctx: Ctx }) {
  const [mem, setMem] = useState<Memory[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<Memory[]>("/memory").then(setMem).catch((e) => setErr(errMsg(e))); }, [ctx.bump]);
  const outcome = (m: Memory) => { const o = window.prompt("Outcome: CLEARED / CONSULTATION / DISPUTE / AMENDED", m.outcome); const r = o && ask("Lý do"); if (o && r) post(`/memory/${m.id}/outcome`, { outcome: o.toUpperCase(), reason: r }).then(() => { ctx.toast("Đã ghi outcome"); ctx.refresh(); }).catch((e) => setErr(errMsg(e))); };
  return (
    <Card title="Historical Learning" right={<span className="badge purple">Approved-only</span>}>
      {err && <p className="err">{err}</p>}
      <table><thead><tr><th>Model</th><th>Approved HS</th><th>Last value</th><th>Outcome</th><th>Use now</th><th>Case</th></tr></thead><tbody>
        {mem.map((m) => (<tr key={m.id}><td>{m.model ?? "—"}<div className="mini">{m.description}</div></td><td>{m.hs_code}</td><td>{m.unit_price} {m.currency}</td>
          <td><Badge s={m.outcome} />{ctx.can("memory.outcome") && <> <a href="#" onClick={(e) => { e.preventDefault(); outcome(m); }}>đặt</a></>}</td>
          <td>{m.reusable ? <Badge s="PASS">Reference</Badge> : <Badge s="BLOCKED">Do not auto-copy</Badge>}</td><td className="mini">{m.case_no}<br />{m.approved_at.slice(0, 10)}</td></tr>))}
        {!mem.length && <tr><td colSpan={6} className="mini">Bộ nhớ trống — chỉ các quyết định HS được reviewer duyệt mới được ghi.</td></tr>}
      </tbody></table>
    </Card>
  );
}
