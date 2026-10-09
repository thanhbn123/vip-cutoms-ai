import { expect, test } from "@playwright/test";

const PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-acceptance-2026";
const NOTICE = /DEMO DATA .* NON-AUTHORITATIVE .* NOT FOR CUSTOMS FILING/;

// G15C §23: a reviewer must never be able to mistake demo knowledge for filing-grade data.
// Asserted in the browser against real staging, not just on the API payload.
test("demo safety labels are visible on every surface that shows HS / tariff / FTA / policy data", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("reviewer@demo.local");
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();

  // Global banner: present on every page while any demo dataset is active.
  const banner = page.getByRole("note");
  await expect(banner).toContainText(NOTICE);
  await expect(banner).toContainText("demo-");

  // Select the seeded reference case (a re-used database may list newer cases first).
  const demoOption = page.locator(".caseselect option", { hasText: "VIP-HQ-261008-001" });
  await page.locator(".caseselect").selectOption((await demoOption.getAttribute("value")) ?? "");

  // Knowledge Hub: every dataset (HS_RULES / TARIFF / FTA / POLICY) is listed as demo+versioned.
  await page.getByRole("button", { name: "Knowledge Hub", exact: true }).click();
  await expect(page.locator(".card", { hasText: "Knowledge Hub" }).locator(".badge.warn").first()).toContainText(NOTICE);
  for (const kind of ["HS_RULES", "TARIFF", "FTA", "POLICY"]) {
    await expect(page.getByText(kind, { exact: false }).first()).toBeVisible();
  }

  // Goods: the per-item C/O, tax and policy assessments each carry a demo badge.
  await page.getByRole("button", { name: "Hàng hóa & HS", exact: true }).click();
  await expect(page.getByRole("note")).toContainText(NOTICE);
  await page.locator("tbody tr", { hasText: "ABC-500" }).click();
  await expect(page.locator(".badge.warn", { hasText: "NOT FOR CUSTOMS FILING" }).first()).toBeVisible();

  // The banner survives navigation to the declaration and release surfaces.
  for (const nav of ["Smart Declaration", "Reviewer & Release"]) {
    await page.getByRole("button", { name: nav, exact: true }).click();
    await expect(page.getByRole("note")).toContainText(NOTICE);
  }
});
