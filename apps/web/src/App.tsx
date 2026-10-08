import { useCallback, useEffect, useState } from "react";
import { api, ApiError, getToken, recall, remember, setToken, type Case, type DemoNotice, type Me } from "./api";
import { Login } from "./Login";
import { NAV, type PageId } from "./nav";
import { CasePage } from "./pages/CasePage";
import { Copilot } from "./pages/Copilot";
import { Declaration } from "./pages/Declaration";
import { Goods } from "./pages/Goods";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Knowledge } from "./pages/Knowledge";
import { Manage } from "./pages/Manage";
import { Review } from "./pages/Review";

export interface Ctx { me: Me; caseId: string | null; cases: Case[]; can: (p: string) => boolean; toast: (m: string) => void; go: (p: PageId) => void; refreshCases: () => Promise<void>; selectCase: (id: string) => void; bump: number; refresh: () => void }

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [env, setEnv] = useState("…");
  const [page, setPage] = useState<PageId>((recall("vip.page") as PageId) || "home");
  const [cases, setCases] = useState<Case[]>([]);
  const [caseId, setCaseId] = useState<string | null>(recall("vip.case"));
  const [msg, setMsg] = useState<string | null>(null);
  const [bump, setBump] = useState(0);
  const [checked, setChecked] = useState(false);
  const [demo, setDemo] = useState<DemoNotice | null>(null);
  useEffect(() => { if (me) api<DemoNotice>("/knowledge/notice").then(setDemo).catch(() => setDemo(null)); }, [me, bump]);

  useEffect(() => {
    fetch("/ready").then((r) => r.json()).then((b) => setEnv(b.checks?.environment ?? b.status)).catch(() => setEnv("api unreachable"));
    if (!getToken()) { setChecked(true); return; }
    api<Me>("/auth/me").then(setMe).catch(() => setToken(null)).finally(() => setChecked(true));
  }, []);
  const refreshCases = useCallback(async () => {
    if (!me) return;
    const list = await api<Case[]>("/cases");
    setCases(list);
    if (list.length && !list.some((c) => c.id === caseId)) { setCaseId(list[0].id); remember("vip.case", list[0].id); }
  }, [me, caseId]);
  useEffect(() => { refreshCases().catch(() => undefined); }, [refreshCases, bump]);

  const toast = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 2200); };
  const go = (p: PageId) => { setPage(p); remember("vip.page", p); window.scrollTo({ top: 0 }); };
  const ctx: Ctx = {
    me: me!, caseId, cases, can: (p) => !!me?.permissions.includes(p), toast, go, refreshCases,
    selectCase: (id) => { setCaseId(id); remember("vip.case", id); setBump((b) => b + 1); }, bump, refresh: () => setBump((b) => b + 1),
  };
  if (!checked) return <div className="main">Đang tải…</div>;
  if (!me) return <Login env={env} onLogin={(m) => { setMe(m); go("home"); }} />;

  const cur = cases.find((c) => c.id === caseId);
  const Page = { home: Home, case: CasePage, declaration: Declaration, goods: Goods, knowledge: Knowledge, copilot: Copilot, review: Review, history: History, manage: Manage }[page];
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">VIP Customs AI<small>V12 · {env} · {me.user.role}</small></div>
        <div className="menu">
          {NAV.map((n) => (<button key={n.id} className={"nav" + (page === n.id ? " active" : "")} onClick={() => go(n.id)}>{n.label}</button>))}
          <button className="nav" onClick={() => { setToken(null); setMe(null); }}>Đăng xuất</button>
        </div>
      </aside>
      <main className="main">
        {demo?.demo_active && <div className="demo-banner" role="note">⚠ {demo.notice} · bộ quy tắc đang dùng: {demo.datasets.join(", ")} — mọi giá trị HS/thuế/C/O/chính sách chỉ để nghiệm thu quy trình.</div>}
        <div className="top">
          <div>
            <h1>{NAV.find((n) => n.id === page)?.label}</h1>
            <div className="sub">Một luồng thống nhất: chứng từ → AI map → HS/C/O/policy → reviewer → tờ khai nháp → lịch sử học lại.</div>
          </div>
          <div className="actions">
            <select className="caseselect" value={caseId ?? ""} onChange={(e) => ctx.selectCase(e.target.value)} aria-label="Hồ sơ hiện tại">
              {!cases.length && <option value="">— chưa có hồ sơ —</option>}
              {cases.map((c) => (<option key={c.id} value={c.id}>{c.case_no} · {c.status}</option>))}
            </select>
            {cur && <span className={`badge ${["BLOCKED"].includes(cur.status) ? "bad" : ["READY_TO_EXPORT", "DRAFT_EXPORTED", "REVIEWED"].includes(cur.status) ? "ok" : "warn"}`}>{cur.status}</span>}
            <button className="btn secondary" onClick={() => { ctx.refresh(); toast("Đã làm mới hồ sơ"); }}>Làm mới</button>
            <button className="btn dark" onClick={() => go("copilot")}>Hỏi AI</button>
            <button className="btn primary" onClick={() => go("review")}>Kiểm tra phát hành</button>
          </div>
        </div>
        <ErrorBoundaryLite key={page + (caseId ?? "") + bump}><Page ctx={ctx} /></ErrorBoundaryLite>
      </main>
      <div className={"toast" + (msg ? " show" : "")}>{msg}</div>
    </div>
  );
}

function ErrorBoundaryLite({ children }: { children: React.ReactNode }) { return <>{children}</>; }

export function errMsg(e: unknown): string {
  if (e instanceof ApiError) return `${e.code}: ${e.message}${e.details && typeof e.details === "object" && "checks" in (e.details as object) ? " — " + ((e.details as { checks: { message: string }[] }).checks.map((c) => c.message).join("; ")) : ""}`;
  return e instanceof Error ? e.message : String(e);
}
