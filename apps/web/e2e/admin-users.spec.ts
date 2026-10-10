import { expect, test } from "@playwright/test";

const PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "demo-acceptance-2026";
const stamp = Date.now().toString(36);
const EMAIL = `e2e-${stamp}@example.test`;

// G18F/G18G/G18H in the browser: tenant-code login, account lifecycle with mandatory reasons, tenant audit feed.
test("admin logs in with the tenant code, creates / re-roles / deactivates a colleague, and the tenant audit shows it", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("admin@demo.local");
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByText("Đăng nhập theo mã tenant").click();
  await page.getByLabel("Mã tenant").fill("demo");  // case-insensitive
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.locator(".sidebar .logo")).toContainText("ADMIN · DEMO");  // role · tenant of the session (G18F-2)

  await page.getByRole("button", { name: "Quản trị", exact: true }).click();
  await expect(page.getByText("(bạn)")).toBeVisible();  // the admin's own row carries no self-locking controls

  // every lifecycle action asks for a reason through window.prompt
  page.on("dialog", (d) => d.accept(d.message().startsWith("Mật khẩu mới") ? "temporary-pass-123" : "e2e reason text"));

  await page.getByRole("button", { name: "Tạo tài khoản" }).click();
  await page.getByLabel("Email", { exact: true }).last().fill(EMAIL);
  await page.getByLabel("Họ tên").fill("E2E Colleague");
  await page.getByLabel("Vai trò", { exact: true }).selectOption("OPERATOR");
  await page.getByLabel("Mật khẩu ban đầu (≥10 ký tự)").fill("initial-pass-1");
  await page.getByRole("button", { name: "Tạo", exact: true }).click();
  const row = page.locator("tr", { hasText: EMAIL });
  await expect(row).toBeVisible();

  await row.getByLabel(`Vai trò ${EMAIL}`).selectOption("REVIEWER");
  await expect(row.getByLabel(`Vai trò ${EMAIL}`)).toHaveValue("REVIEWER");

  await row.getByText("vô hiệu hoá").click();
  await expect(row.locator(".badge", { hasText: "inactive" })).toBeVisible();
  await expect(row.getByText("kích hoạt lại")).toBeVisible();

  // tenant-level audit feed (default scope) lists the account events with their reasons
  const auditCard = page.locator(".card", { hasText: "Audit" });
  await expect(auditCard).toContainText("user.deactivated");
  await expect(auditCard).toContainText("user.updated");
  await expect(auditCard).toContainText("user.created");
  await expect(auditCard).toContainText("e2e reason text");

  // the deactivated colleague cannot log in; the generic error carries no hint
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill("initial-pass-1");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.locator(".callout.critical")).toContainText(/invalid email, tenant or password/);
});
