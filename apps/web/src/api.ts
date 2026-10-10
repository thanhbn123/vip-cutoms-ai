// Thin API client. Token lives in localStorage (per-viewer convenience); the server is the authority on every action.
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

const KEY = "vip.token";
export function getToken(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}
export function remember(key: string, value: string | null) {
  try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch { /* ignore */ }
}
export function recall(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }  // proxy HTML (502/504/413) is not JSON
  if (res.ok && text && body === null) throw new ApiError(res.status, "BAD_RESPONSE", "Phản hồi không phải JSON (proxy/SPA fallback?)");
  if (!res.ok) {
    if (body === null) throw new ApiError(res.status, "UPSTREAM", text ? `Máy chủ trả về lỗi ${res.status} (không phải JSON)` : res.statusText);
    const d = body?.detail;
    if (Array.isArray(d)) throw new ApiError(res.status, "VALIDATION", d.map((e: { msg: string; loc: string[] }) => `${e.loc?.slice(-1)[0]}: ${e.msg}`).join("; "), d);
    throw new ApiError(res.status, d?.code ?? "ERROR", d?.message ?? res.statusText, d?.details);
  }
  return body as T;
}

export const post = <T = unknown>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T = unknown>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T = unknown>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

export function uploadDocument(caseId: string, docType: string, file: File) {
  const fd = new FormData();
  fd.append("doc_type", docType);
  fd.append("file", file);
  return api(`/cases/${caseId}/documents`, { method: "POST", body: fd });
}

// ---- shared types (subset of the API schemas)
export interface User { id: string; email: string; full_name: string; role: string; tenant_id: string; tenant_code?: string | null }
export interface Me { user: User; permissions: string[] }
export interface Case { id: string; case_no: string; status: string; declaration_type: string; customs_office: string | null; customer_id: string; supplier_id: string | null; priority: string; owner_id: string; reviewer_id: string | null; created_at: string }
export interface Doc { id: string; doc_type: string; filename: string; version: number; status: string; parse_confidence: number | null; parse_warnings: string[]; sha256: string }
export interface Field { id?: string; key: string; label: string; section: string; value: string | null; confidence: number | null; is_critical: boolean; review_status: string; origin: string | null; source?: { document_id?: string | null; source_ref?: string | null } | null; source_ref?: string | null; reasoning: string | null; rule_ref?: string | null; alternatives: { value: string; doc_type: string }[] }
export interface Candidate { id: string; rank: number; heading: string; title: string; confidence: number; reasoning: string[]; missing_attributes: string[]; history_refs: { case_no: string; hs_code: string; match: string; reusable: boolean; outcome: string }[]; dataset_version: string; status: string }
export interface Item { id: string; line_no: number; description: string; description_vn: string | null; description_vn_status: string; model: string | null; quantity: string | null; unit: string | null; unit_price: string | null; amount: string | null; attributes: Record<string, { value: string; source: string }>; hs_code: string | null; hs_status: string; hs_confidence: number | null; co_line_matched: boolean | null; origin_criterion: string | null; source_ref: string | null; candidates: Candidate[] }
export interface Issue { id: string; code: string; severity: string; category: string; title: string; detail: string | null; target_ref: string | null; status: string; assignee_role: string | null; resolution: string | null; auto_resolvable?: boolean }
export interface Assessment { id: string; item_id: string | null; kind: string; status: string; dataset_version: string | null; dataset_is_demo: boolean | null; inputs: Record<string, unknown>; result: Record<string, unknown>; reasoning: string[]; reviewer_decision: { decision: string } | null }
export interface Declaration { case: { case_no: string; status: string }; readiness: number; summary: { fields_total: number; fields_ok: number; items_total: number; items_hs_approved: number; open_critical: number; open_warning: number; documents: Doc[] }; sections: { id: string; title: string; fields: Field[] }[]; items: unknown[]; validation: { code: string; ok: boolean; severity: string; message: string }[]; release_eligible: boolean; disclaimer: string }
export interface Dataset {
  id: string; kind: string; version: string; label: string; source: string; is_demo: boolean; effective_from: string; effective_to: string | null; is_active: boolean; rule_count: number;
  // G18 provenance (older API builds omit these)
  is_authoritative?: boolean; source_authority?: string | null; source_document?: string | null; source_reference?: string | null;
  ingested_at?: string | null; verified_at?: string | null; verified_by?: string | null; checksum?: string | null; supersedes_id?: string | null; superseded_at?: string | null;
}
export interface Draft { id: string; version: number; kind: string; release_eligible: boolean; watermark: string; checksum: string; created_at: string }
export interface Memory { id: string; model: string | null; description: string; hs_code: string; unit_price: string | null; currency: string | null; outcome: string; reusable: boolean; case_no: string; approved_at: string }
export interface Proposal { id: string; target_ref: string; current_value: string | null; proposed_value: string; status: string; reasoning: string[]; requested_by: string }
export interface Message { id: string; role: string; content: string; intent: string | null; provider: string | null; sources: { type: string; label: string }[]; reasoning: string[]; proposal_id: string | null; meta: { confidence?: number; recommended_actions?: string[]; requires_review?: boolean } }
export interface QueueRow { case_id: string; case_no: string; status: string; priority: string; open_critical: number; open_warning: number; top_issues: Issue[] }
export interface DemoNotice {
  demo_active: boolean; notice: string | null; datasets: string[]; non_demo_datasets: string[];
  // G18 runtime mode (demo | limited | full). Older API builds omit these fields.
  app_mode?: "demo" | "limited" | "full"; mode_notice?: string | null; real_filing_decisions?: boolean; mock_ai_active?: boolean;
  authoritative_datasets?: string[];
}
