import { useEffect, useState } from "react";
import { NAV, type PageId } from "./nav";

export function App() {
  const [page, setPage] = useState<PageId>("home");
  const [health, setHealth] = useState("checking…");
  useEffect(() => {
    fetch("/ready")
      .then((r) => r.json())
      .then((b) => setHealth(b.status))
      .catch(() => setHealth("api unreachable"));
  }, []);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          VIP Customs AI<small>V12 · G01 shell</small>
        </div>
        <div className="menu">
          {NAV.map((n) => (
            <button key={n.id} className={"nav" + (page === n.id ? " active" : "")} onClick={() => setPage(n.id)}>
              {n.label}
            </button>
          ))}
        </div>
      </aside>
      <main className="main">
        <div className="top">
          <div>
            <h1>{NAV.find((n) => n.id === page)?.label}</h1>
            <div className="sub">API: {health}</div>
          </div>
        </div>
      </main>
    </div>
  );
}
