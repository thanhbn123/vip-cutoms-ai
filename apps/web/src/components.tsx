import type { ReactNode } from "react";

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

const TONE: Record<string, string> = {
  APPROVED: "ok", AUTO_ACCEPTABLE: "ok", PASS: "ok", COMPUTED: "ok", REVIEWED: "ok", READY_TO_EXPORT: "ok", DRAFT_EXPORTED: "ok", CLEARED: "ok", RESOLVED: "ok", ELIGIBLE_PENDING_REVIEW: "ok", NO_REQUIREMENT: "ok",
  NEEDS_REVIEW: "warn", REVIEW_REQUIRED: "warn", WARNING: "warn", PENDING_HS: "warn", INPUT_MISSING: "warn", AWAITING_HS: "warn", WAIVED: "warn", REQUIREMENTS_PENDING_REVIEW: "warn", UNKNOWN: "warn", CONSULTATION: "warn", PROPOSED: "warn", MANUAL: "warn",
  BLOCKED: "bad", CRITICAL: "bad", REJECTED: "bad", PARSE_FAILED: "bad", UNDETERMINED: "bad", DISPUTE: "bad", MISSING: "bad",
  NEW: "info", DOCUMENTS_UPLOADED: "info", AI_PROCESSING: "info", UPLOADED: "info", PARSED: "info", OPEN: "info", NOT_COVERED: "info",
};
export function Badge({ s, children }: { s?: string; children?: ReactNode }) {
  const tone = TONE[s ?? ""] ?? "purple";
  return <span className={`badge ${tone}`}>{children ?? s}</span>;
}
export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`card ${className}`}>
      {(title || right) && (<div className="section-title"><h2>{title}</h2>{right}</div>)}
      {children}
    </div>
  );
}
export function Metric({ label, value, badge }: { label: string; value: ReactNode; badge?: ReactNode }) {
  return (<div className="card metric"><div className="l">{label}</div><div className="v">{value}</div>{badge}</div>);
}
export function Callout({ kind, children }: { kind: "critical" | "warning" | "pass"; children: ReactNode }) {
  return <div className={`callout ${kind}`}>{children}</div>;
}
export function Flow({ steps, on }: { steps: string[]; on: string[] }) {
  return (<div className="flow">{steps.map((s) => (<span key={s} className={`step${on.includes(s) ? " on" : ""}`}>{s}</span>))}</div>);
}
export function Gap() { return <div style={{ height: 12 }} />; }
export function Row({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (<div className="row"><strong>{title}</strong>{children && <p>{children}</p>}</div>);
}
export function ask(label: string, def = ""): string | null {
  const v = window.prompt(label, def);
  return v && v.trim().length >= 5 ? v.trim() : null;
}
