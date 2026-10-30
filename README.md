# Chợ địa phương số (Flask + SQLite)

Website thương mại điện tử cho chợ truyền thống, xây theo 5 luồng nghiệp vụ và Chương 3 phân tích yêu cầu.

## Chạy trong Visual Studio Code
```bash
cd cho_so
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Mở http://127.0.0.1:5000. Lần chạy đầu tự tạo `cho_so.db` và dữ liệu mẫu. Muốn làm lại từ đầu: xoá file `cho_so.db`.
Có thể bấm F5 trong VS Code (đã cấu hình `.vscode/launch.json`).

## Tài khoản demo (mật khẩu 123456)
| Vai trò | Email |
|---|---|
| Khách hàng | khach@cho.vn |
| Người bán (gian hàng đã hoạt động) | banhang1@cho.vn, banhang2@cho.vn, banhang3@cho.vn |
| Người bán (hồ sơ chờ duyệt) | banhang4@cho.vn |
| Ban quản lý chợ | bql@cho.vn |
| Đơn vị vận hành | operator@cho.vn |
| Shipper | shipper1@cho.vn, shipper2@cho.vn, shipper3@cho.vn |
| Quản trị | admin@cho.vn |

## Luồng nghiệp vụ → chức năng
1. **Đăng ký gian hàng số**: Người bán nộp hồ sơ + minh chứng → BQL kiểm tra (đạt / yêu cầu bổ sung / từ chối) → hệ thống xác thực và tính phí theo ngành hàng & thời hạn → thanh toán phí → BQL phê duyệt → gian hàng ACTIVE.
2. **Mua hàng & đặt hàng**: tìm kiếm, giỏ hàng nhiều gian hàng, yêu cầu bổ sung, địa chỉ, hình thức giao (tự lấy / giao ngay / tiết kiệm), thanh toán (COD, QR, ví – giả lập). Hệ thống tách thành đơn theo từng Merchant và gửi thông báo.
3. **Merchant xử lý đơn**: xác nhận hoặc từ chối/hết hàng → chuẩn bị → sẵn sàng → đặt ship → bàn giao → theo dõi → hoàn tất. Quản lý sản phẩm, giá, tồn kho, doanh thu ngày/tháng.
4. **Giao hàng địa phương & gom đơn**: Operator tìm shipper gần nhất cho đơn giao ngay; gom đơn tiết kiệm theo khu vực, khung giờ, loại hàng tương thích và tải trọng; Shipper nhận hàng, giao, thu COD; Operator đối soát COD.
5. **Truy xuất nguồn gốc**: nhà cung cấp → lô hàng (xác minh bởi BQL) → sản phẩm → đơn hàng. Trang `/truy-xuat` tra theo mã lô; BQL/Admin thấy danh sách đơn bị ảnh hưởng để thu hồi.

## Cấu trúc
```
app.py  config.py  models.py  helpers.py  seed.py  test_flow.py
routes/ (shop, auth, merchant, bql, ops, admin)
templates/  static/css/style.css  uploads/
```
Chạy kiểm thử luồng: `python test_flow.py` (xoá `cho_so.db` sau khi chạy để trả về dữ liệu mẫu sạch).

## Khi đưa lên môi trường thật
Đặt biến môi trường `SECRET_KEY`, chuyển sang PostgreSQL/MySQL (đổi `SQLALCHEMY_DATABASE_URI`), thêm bảo vệ CSRF (Flask-WTF), chạy bằng gunicorn/waitress, tích hợp cổng thanh toán thật.
