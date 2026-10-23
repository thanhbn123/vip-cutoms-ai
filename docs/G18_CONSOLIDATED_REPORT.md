# Báo cáo tổng hợp — VIP Customs AI (G16 → G18J)

Ngày lập: 2026-10-23 · Người lập: project controller (Claude Code) · Gắn với SHA bên dưới, không suy diễn trạng thái.

## 1. Trạng thái một dòng

`develop` = `49fd2ab` (CI run 38377437255: 6/6 job xanh) · `main` = `4a2acb9` (đóng băng từ G17, owner duyệt) ·
production **chưa triển khai** · staging vẫn chạy image G15C (`9649ec7`), **chưa redeploy** lên develop hiện tại ·
chế độ chạy mặc định `APP_MODE=limited`, AI = mock, dữ liệu hải quan = demo có nhãn NON-AUTHORITATIVE.

Toàn bộ việc kỹ thuật không cần owner đã xong. Phần còn lại đều chờ quyết định hoặc thông tin từ owner (mục 5).

## 2. Các gate đã hoàn thành

| Gate | Nội dung chính | SHA kết thúc |
|---|---|---|
| G16 | Review PR #1, đóng băng Release Candidate, mở PR #2 develop → main | `54a00e7` |
| G17 | Owner duyệt, merge PR #2 vào main, đóng băng RC (tag `v0.1.0-rc1` chỉ có local, push bị từ chối) | main `4a2acb9` |
| G18A | Chế độ `demo/limited/full`, FULL từ chối khởi động nếu thiếu provider thật/ngân sách/backup; 4 ranh giới AI + adapter `http-llm`; quản trị dữ liệu có thẩm quyền (migration 0011); công cụ B-07; thiết kế backup off-host, monitoring, quyền deploy, secrets | — |
| G18B | Hardening: token lỗi → 401, security header, ledger chi phí AI bền (migration 0012), `knowledge.verify` cho Senior | — |
| G18C | Review toàn bộ diff G18: 20 + 14 phát hiện đã xử lý (issue hệ thống không thể "resolve" tay, quyết định sau export mở lại hồ sơ, `/metrics` đóng mặc định…) | — |
| G18D–E | Chống brute-force đăng nhập 3 chiều (cặp IP+email, email, IP), audit khi khoá; Knowledge Hub cho data steward; clean checkout từ zero | `398a4ba` |
| G18F | **Đăng nhập theo tenant** (owner yêu cầu): email duy nhất theo tenant (migration 0013), mã tenant tuỳ chọn, đóng lỗ dò email chéo tenant | `e4feebd` |
| G18F-2 | Tự review: header hiện tenant, chọn tenant khi trùng email, audit khoá đúng tài khoản thật, +2 negative test | `3f2a502` |
| G18G | **Vòng đời tài khoản**: ADMIN đổi tên/vai trò, vô hiệu hoá/kích hoạt, đặt lại mật khẩu; người dùng tự đổi mật khẩu; token cũ bị huỷ khi đổi mật khẩu (migration 0014); không thể tự khoá admin | `7c823c4` |
| G18H | Audit cấp tenant đọc được trên UI (`GET /audit`); Playwright cho luồng tenant + tài khoản; **E2E chạy trong CI** | `ae37e61` |
| G18I | Bộ nghiệm thu owner mở rộng A–P → **A–R** (Q: đăng nhập tenant, R: vòng đời tài khoản + audit) | `d19a0de` |
| G18J | **Audit lỗ hổng phụ thuộc**: 8 cảnh báo công cụ dev → 0 (Vite 8, Vitest 5, Playwright 1.64); API sạch; job CI `deps-audit` | `49fd2ab` |

Quyết định mới được ghi trong `docs/DECISIONS.md`: D-033 → D-045. Migration hiện tại: `0014_password_changed_at` (một head).

## 3. Bằng chứng kiểm thử trên `49fd2ab`

| Bộ kiểm thử | Kết quả |
|---|---|
| Backend pytest (PostgreSQL thật) | 187 passed, 1 skipped |
| Frontend vitest | 16/16 |
| Hạ tầng (`tests/` gốc: backup, compose, systemd) | 108/108 |
| Playwright (trình duyệt thật) | 3/3 native, 3/3 trên Docker, và chạy trong CI |
| Nghiệm thu HTTP owner A–R | 19/19 (native + Docker) |
| Negative / bảo mật | 20/20 |
| Docker smoke từ volume rỗng | build OK, migrate tới 0014, 0 restart, 0 lộ secret |
| Secret scan | sạch |
| Audit phụ thuộc (`scripts/deps_audit.sh`) | CLEAN |
| CI GitHub Actions | api · web · infra · e2e · secrets · deps-audit đều xanh |

File bằng chứng: `artifacts/test-results/g18*.txt`.

## 4. Những gì sản phẩm làm được hôm nay (limited mode)

- Hồ sơ hải quan: upload chứng từ, trích xuất có nguồn/độ tin cậy, phát hiện lệch số kiện, gợi ý HS có bằng chứng, chặn khi thiếu bằng chứng, reviewer duyệt có lý do, tính trị giá, C/O + policy theo dữ liệu có phiên bản, bản nháp tờ khai nội bộ có watermark, Copilot trả lời có nguồn, học lịch sử chỉ từ kết quả đã duyệt.
- Tài khoản & bảo mật: đa tenant cô lập ở truy vấn, đăng nhập theo tenant không lộ thông tin, chống brute-force, quản lý tài khoản qua UI có audit, huỷ token khi đổi mật khẩu, chuỗi audit chống sửa có thể kiểm tra trên UI.
- Vận hành: `/health`, `/ready` theo chế độ, `/metrics`, backup có quyền 0600 + thiết kế off-host, runbook triển khai/rollback, nghiệm thu một lệnh.

## 5. Việc đang chờ owner (không thể làm thay)

| Mã | Cần gì từ owner | Mở khoá điều gì |
|---|---|---|
| B-01 | Chọn nhà cung cấp AI: endpoint, model, API key, giá, thoả thuận xử lý dữ liệu | Trích xuất/HS/Copilot thật thay mock |
| B-02 | Chọn nguồn dữ liệu biểu thuế/FTA/chính sách có giấy phép, người nhập liệu, người xác minh | Bỏ dữ liệu demo, tiến tới chế độ FULL |
| B-06 | Chọn host production (khuyến nghị VPS riêng), domain, TLS | Gate G19 |
| Backup / monitoring | Đích lưu off-host + khoá mã hoá; kênh nhận cảnh báo | Backup ngoài máy, cảnh báo |
| Staging | Operator có khoá `deploy` redeploy staging lên `49fd2ab` (session này không SSH được) | Chạy nghiệm thu A–R thật và B-07 |
| B-07 | Xác nhận đã nghiệm thu xong để vô hiệu hoá 4 tài khoản demo (làm được ngay trên UI sau khi redeploy) | Đóng B-07 |
| Tag | Quyền push tag `v0.1.0-rc1` | Đánh dấu RC trên GitHub |
| main | Duyệt merge develop → main lần tiếp theo | Đưa G18 vào nhánh phát hành |

Chi tiết từng input: `docs/G18_OWNER_INPUTS.md`. Quy trình operator: `docs/NEXT_SESSION_G18B_OPERATOR.md`.

## 6. Giới hạn đã biết (ghi trung thực)

- Throttle đăng nhập nằm trong bộ nhớ một tiến trình; scale nhiều container cần lớp chia sẻ hoặc giới hạn ở proxy.
- Chưa gửi email (chưa có nhà cung cấp mail); mật khẩu reset trao tay. Chính sách mật khẩu mới chỉ là độ dài ≥10.
- Huỷ token theo độ chính xác 1 giây.
- Job `deps-audit` trong CI chỉ mang tính thông báo; trước release phải chạy CLEAN.
- OCR ảnh scan chưa có provider; scan bị đánh dấu cần xử lý tay (fail closed).
- Không có tích hợp VNACCS/ECUS; mọi đầu ra chỉ là bản nháp nội bộ.

## 7. Gate tiếp theo

**G19 — dựng production ở chế độ limited**, cần B-06 + đích backup/monitoring. Song song, operator redeploy staging lên
`49fd2ab` và chạy `scripts/staging/acceptance.sh` (kỳ vọng A–R 19/19, negative 20/20), sau đó đóng B-07 trên UI.
