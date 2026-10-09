// Sidebar order and labels are taken verbatim from V12 FINAL (prototype/index.html).
export const NAV = [
  { id: "home", label: "Tổng quan" },
  { id: "case", label: "Hồ sơ & chứng từ" },
  { id: "declaration", label: "Smart Declaration" },
  { id: "goods", label: "Hàng hóa & HS" },
  { id: "knowledge", label: "Knowledge Hub" },
  { id: "copilot", label: "AI Copilot" },
  { id: "review", label: "Reviewer & Release" },
  { id: "history", label: "Lịch sử & Learning" },
  { id: "manage", label: "Quản trị" },
] as const;

export type PageId = (typeof NAV)[number]["id"];
