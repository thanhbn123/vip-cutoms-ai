import { expect, test } from "@playwright/test";

const PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-acceptance-2026";

test("login → V12 navigation → goods shows the BLOCKED item → copilot answers → release gate blocked", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("reviewer@demo.local");
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();

  const nav = ["Tổng quan", "Hồ sơ & chứng từ", "Smart Declaration", "Hàng hóa & HS", "Knowledge Hub", "AI Copilot", "Reviewer & Release", "Lịch sử & Learning", "Quản trị"];
  for (const n of nav) await expect(page.getByRole("button", { name: n, exact: true })).toBeVisible();
  await expect(page.locator(".caseselect")).toContainText("VIP-HQ-261008-001");
  await expect(page.locator(".top .badge")).toHaveText("BLOCKED");

  await page.getByRole("button", { name: "Hàng hóa & HS", exact: true }).click();
  const row3 = page.locator("tbody tr", { hasText: "CT-88" });
  await expect(row3).toContainText("8537.xx.xx");
  await expect(row3).toContainText("64%");
  await expect(row3.locator(".badge")).toHaveText("BLOCKED");
  await expect(page.locator("tbody tr", { hasText: "ABC-500" })).toContainText("87%");
  await expect(page.locator("tbody tr", { hasText: "PVC-20" })).toContainText("95%");

  await page.getByRole("button", { name: "AI Copilot", exact: true }).click();
  await page.getByRole("button", { name: "Còn thiếu gì để khai?" }).click();
  await expect(page.locator(".msg.ai").last()).toContainText("Item 3", { timeout: 15_000 });
  await expect(page.locator(".msg.ai").last()).toContainText("requires review");

  await page.getByRole("button", { name: "Kiểm tra phát hành" }).click();
  await expect(page.locator(".card", { hasText: "Release Gate" }).locator(".section-title .badge")).toHaveText("BLOCKED");
  await expect(page.getByRole("button", { name: "Phát hành bản nháp" })).toBeDisabled();

  await page.getByRole("button", { name: "Smart Declaration", exact: true }).click();
  await expect(page.locator("input[value='INV-2026-889']")).toBeVisible();
});
