"""Kiểm thử nhanh toàn bộ luồng nghiệp vụ:  python test_flow.py"""
import io, os
os.environ.setdefault("X", "1")
from app import app
from models import DeliveryRequest, Product, Stall, SubOrder, db


def login(c, email):
    c.get("/dang-xuat")
    r = c.post("/dang-nhap", data={"email": email, "password": "123456"})
    assert r.status_code == 302, email


def ok(r, code=(200, 302)):
    assert r.status_code in code, (r.request.path, r.status_code, r.data[:300])
    return r


def run():
    c = app.test_client()
    # trang công khai
    for u in ["/", "/san-pham", "/san-pham?q=rau", "/san-pham/1", "/gian-hang/1", "/truy-xuat?code=LO-2610-001", "/dang-nhap", "/dang-ky", "/gio-hang"]:
        ok(c.get(u), (200,))

    # Luồng 1: đăng ký gian hàng
    r = c.post("/dang-ky", data={"role": "merchant", "full_name": "Anh Test", "email": "t@cho.vn", "password": "123456"}); ok(r)
    ok(c.get("/merchant/"), (200,))
    ok(c.get("/merchant/gian-hang"), (200,))
    r = c.post("/merchant/gian-hang", data={"name": "Test Stall", "market_id": 1, "category_id": 1, "months": 6, "docs": (io.BytesIO(b"x"), "gp.pdf")}, content_type="multipart/form-data"); ok(r)
    with app.app_context():
        st = Stall.query.filter_by(name="Test Stall").first(); sid = st.id; assert st.status == "submitted"
    login(c, "bql@cho.vn"); ok(c.get("/bql/"), (200,)); ok(c.get(f"/bql/gian-hang/{sid}"), (200,))
    ok(c.post(f"/bql/gian-hang/{sid}/xu-ly", data={"action": "need_more", "note": "Thiếu ảnh"}))
    login(c, "t@cho.vn"); ok(c.get("/merchant/"), (200,))
    ok(c.post("/merchant/gian-hang", data={"name": "Test Stall", "market_id": 1, "category_id": 1, "months": 6}, content_type="multipart/form-data"))
    login(c, "bql@cho.vn"); ok(c.post(f"/bql/gian-hang/{sid}/xu-ly", data={"action": "pass"}))
    login(c, "t@cho.vn"); ok(c.get("/merchant/gian-hang/thanh-toan"), (200,)); ok(c.post("/merchant/gian-hang/thanh-toan"))
    login(c, "bql@cho.vn"); ok(c.post(f"/bql/gian-hang/{sid}/xu-ly", data={"action": "approve"}))
    login(c, "t@cho.vn"); ok(c.get("/merchant/"), (200,)); ok(c.get("/merchant/san-pham"), (200,)); ok(c.get("/merchant/san-pham/moi"), (200,))
    ok(c.post("/merchant/nguon-goc", data={"kind": "supplier", "name": "NCC T"}))
    ok(c.get("/merchant/nguon-goc"), (200,))
    ok(c.post("/merchant/san-pham/moi", data={"name": "Sp test", "price": 1000, "stock": 5, "unit": "kg", "is_active": "on"}))

    # Luồng 2: mua hàng nhiều gian hàng, giao tiết kiệm + COD
    login(c, "khach@cho.vn")
    ok(c.post("/gio-hang/them", data={"product_id": 1, "qty": 2})); ok(c.post("/gio-hang/them", data={"product_id": 6, "qty": 1})); ok(c.post("/gio-hang/them", data={"product_id": 11, "qty": 1}))
    ok(c.get("/gio-hang"), (200,)); ok(c.get("/dat-hang"), (200,))
    r = ok(c.post("/dat-hang", data={"receiver_name": "Mai", "phone": "09", "district": "Cầu Giấy", "address": "1 ABC", "delivery_type": "economy", "time_window": "Sáng 8h-11h", "payment_method": "cod", "note": "gọi trước"}))
    with app.app_context():
        subs = SubOrder.query.order_by(SubOrder.id.desc()).limit(3).all(); ids = [s.id for s in subs]; assert len(subs) == 3
    # Luồng 3: merchant xử lý
    for s_id in ids:
        with app.app_context():
            email = db.session.get(SubOrder, s_id).stall.owner.email
        login(c, email); ok(c.get(f"/merchant/don-hang/{s_id}"), (200,))
        for act in ["accept", "prepare", "ready", "request_ship"]:
            ok(c.post(f"/merchant/don-hang/{s_id}/thao-tac", data={"action": act}))
    # Luồng 4: điều phối gom đơn
    login(c, "operator@cho.vn"); ok(c.get("/van-hanh/dieu-phoi"), (200,)); ok(c.post("/van-hanh/gom-don"))
    with app.app_context():
        reqs = DeliveryRequest.query.filter(DeliveryRequest.suborder_id.in_(ids)).all()
        assert all(r.status == "assigned" and r.trip_id for r in reqs), [(r.status, r.trip_id) for r in reqs]
        # cùng quận/khung giờ/hàng: kiểm tra số chuyến
        print("Chuyến:", {r.trip.code: r.handling for r in reqs})
        shipper_email = reqs[0].shipper.email
    for s_id in ids:
        with app.app_context():
            email = db.session.get(SubOrder, s_id).stall.owner.email
        login(c, email); ok(c.post(f"/merchant/don-hang/{s_id}/thao-tac", data={"action": "handover"}))
    with app.app_context():
        rq = [(r.id, r.shipper.email) for r in DeliveryRequest.query.filter(DeliveryRequest.suborder_id.in_(ids)).all()]
    for rid, em in rq:
        login(c, em); ok(c.get("/van-hanh/shipper"), (200,))
        ok(c.post(f"/van-hanh/giao-hang/{rid}/start")); ok(c.post(f"/van-hanh/giao-hang/{rid}/done"))
    login(c, "operator@cho.vn")
    for rid, _ in rq: ok(c.post(f"/van-hanh/doi-soat/{rid}"))
    with app.app_context():
        assert all(s.status == "completed" for s in SubOrder.query.filter(SubOrder.id.in_(ids)))
        o = SubOrder.query.get(ids[0]).order; assert o.status == "completed" and o.payment_status == "paid"; oid = o.id
    login(c, "khach@cho.vn"); ok(c.get(f"/don-hang/{oid}"), (200,)); ok(c.get("/don-hang"), (200,))
    with app.app_context():
        item_id = SubOrder.query.get(ids[0]).items[0].id
    ok(c.post(f"/danh-gia/{item_id}", data={"rating": 5, "comment": "Tươi"})); ok(c.post("/ho-tro", data={"content": "Test", "order_id": oid}))

    # Giao ngay + thanh toán online + từ chối hết hàng
    ok(c.post("/gio-hang/them", data={"product_id": 2, "qty": 1}))
    ok(c.post("/dat-hang", data={"receiver_name": "Mai", "phone": "09", "district": "Cầu Giấy", "address": "1 ABC", "delivery_type": "instant", "payment_method": "bank"}))
    with app.app_context():
        o = db.session.get(SubOrder, SubOrder.query.count()).order; oid = o.id
    ok(c.get(f"/don-hang/{oid}/thanh-toan"), (200,)); ok(c.post(f"/don-hang/{oid}/thanh-toan", data={"result": "success"}))
    with app.app_context():
        s = SubOrder.query.filter_by(order_id=oid).first(); sid2 = s.id; email = s.stall.owner.email; assert s.status == "new"
    login(c, email)
    for act in ["accept", "prepare", "ready", "request_ship"]: ok(c.post(f"/merchant/don-hang/{sid2}/thao-tac", data={"action": act}))
    login(c, "operator@cho.vn"); 
    with app.app_context(): rid = DeliveryRequest.query.filter_by(suborder_id=sid2).first().id
    ok(c.post(f"/van-hanh/giao-ngay/{rid}"))
    # hết hàng
    login(c, "khach@cho.vn"); ok(c.post("/gio-hang/them", data={"product_id": 3, "qty": 1}))
    ok(c.post("/dat-hang", data={"receiver_name": "Mai", "phone": "09", "district": "Cầu Giấy", "address": "1", "delivery_type": "pickup", "payment_method": "cod"}))
    with app.app_context():
        s = SubOrder.query.order_by(SubOrder.id.desc()).first(); sid3, email = s.id, s.stall.owner.email
    login(c, email); ok(c.post(f"/merchant/don-hang/{sid3}/thao-tac", data={"action": "reject", "reason": "Hết hàng"})); ok(c.get("/merchant/don-hang"), (200,)); ok(c.get("/merchant/"), (200,))
    # admin / bql
    login(c, "admin@cho.vn")
    for u in ["/quan-tri/", "/quan-tri/nguoi-dung", "/quan-tri/cho-nganh-hang", "/quan-tri/ho-tro", "/truy-xuat?code=LO-2610-001", "/bql/", "/van-hanh/dieu-phoi", "/auth" if False else "/tai-khoan", "/thong-bao"]:
        ok(c.get(u), (200,))
    login(c, "khach@cho.vn"); assert c.get("/quan-tri/").status_code == 302
    print("TẤT CẢ LUỒNG OK")


with app.app_context():
    pass
run()
