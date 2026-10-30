"""Dữ liệu mẫu – tự chạy lần đầu khi database còn trống."""
import random
from datetime import datetime, timedelta

from models import (Batch, Category, Market, Order, OrderItem, Product, Stall, SubOrder, Supplier, User, db)

PASSWORD = "123456"


def make_user(name, email, role, **kw):
    u = User(full_name=name, email=email, role=role, **kw)
    u.set_password(PASSWORD)
    db.session.add(u)
    return u


def seed_data():
    if User.query.first():
        return
    random.seed(7)
    markets = [
        Market(name="Chợ Đồng Xuân", address="Đồng Xuân, Hoàn Kiếm", district="Hoàn Kiếm"),
        Market(name="Chợ Hôm - Đức Viên", address="79 Phố Huế, Hai Bà Trưng", district="Hai Bà Trưng"),
        Market(name="Chợ Nghĩa Tân", address="Nghĩa Tân, Cầu Giấy", district="Cầu Giấy"),
        Market(name="Chợ Bưởi", address="Bưởi, Tây Hồ", district="Tây Hồ"),
    ]
    cats = [
        Category(name="Rau củ quả", emoji="🥬", fee_per_month=150000, handling="fresh"),
        Category(name="Thịt - cá - hải sản", emoji="🐟", fee_per_month=250000, handling="fresh"),
        Category(name="Gạo - đồ khô", emoji="🌾", fee_per_month=200000, handling="dry"),
        Category(name="Gia vị - nước chấm", emoji="🌶️", fee_per_month=180000, handling="dry"),
        Category(name="Bánh kẹo - đặc sản", emoji="🍡", fee_per_month=220000, handling="dry"),
    ]
    db.session.add_all(markets + cats)
    db.session.flush()

    make_user("Quản trị hệ thống", "admin@cho.vn", "admin")
    make_user("Ban quản lý chợ", "bql@cho.vn", "bql")
    make_user("Đơn vị vận hành", "operator@cho.vn", "operator")
    make_user("Anh Hùng (shipper)", "shipper1@cho.vn", "shipper", district="Hoàn Kiếm", vehicle="Xe máy 29-B1 123.45", phone="0901000001")
    make_user("Anh Nam (shipper)", "shipper2@cho.vn", "shipper", district="Cầu Giấy", vehicle="Xe máy 30-C2 678.90", phone="0901000002")
    make_user("Chị Lan (shipper)", "shipper3@cho.vn", "shipper", district="Hai Bà Trưng", vehicle="Xe điện VinFast", phone="0901000003")
    cust = make_user("Nguyễn Thị Mai", "khach@cho.vn", "customer", phone="0912345678", address="12 Ngõ 34 Trần Quốc Hoàn", district="Cầu Giấy")
    db.session.flush()

    spec = [
        ("Bà Tư - Rau sạch", "banhang1@cho.vn", 0, 0, "🥬", [
            ("Rau muống", "bó", 8000, 60, 0.5, "🥬"), ("Cà chua", "kg", 28000, 40, 1, "🍅"),
            ("Dưa leo", "kg", 22000, 35, 1, "🥒"), ("Cà rốt Đà Lạt", "kg", 30000, 50, 1, "🥕"),
            ("Xoài cát Hòa Lộc", "kg", 65000, 25, 1, "🥭")]),
        ("Ông Sáu - Thịt cá tươi", "banhang2@cho.vn", 1, 1, "🐟", [
            ("Thịt ba chỉ", "kg", 135000, 20, 1, "🥩"), ("Cá chép sống", "kg", 90000, 15, 1, "🐟"),
            ("Tôm sú", "kg", 320000, 10, 1, "🦐"), ("Gà ta thả vườn", "con", 210000, 12, 1.8, "🍗"),
            ("Trứng gà ta (vỉ 10)", "vỉ", 42000, 30, 0.7, "🥚")]),
        ("Cô Hoa - Đồ khô & gia vị", "banhang3@cho.vn", 2, 2, "🌾", [
            ("Gạo Tám Xoan", "kg", 28000, 200, 1, "🌾"), ("Nước mắm Phú Quốc", "chai", 65000, 40, 0.8, "🍶"),
            ("Mộc nhĩ khô", "gói", 35000, 50, 0.2, "🍄"), ("Miến dong", "gói", 45000, 45, 0.4, "🍜"),
            ("Ớt bột Hàn Quốc", "hũ", 38000, 30, 0.2, "🌶️"), ("Bánh cốm Hàng Than", "hộp", 55000, 25, 0.4, "🍡")]),
    ]
    stalls = []
    for i, (name, email, mk, ct, emo, prods) in enumerate(spec):
        owner = make_user(name.split(" - ")[0], email, "merchant", phone=f"09020000{i}")
        db.session.flush()
        st = Stall(owner_id=owner.id, market_id=markets[mk].id, category_id=cats[ct].id, name=name,
                   description="Gian hàng quen thuộc nhiều năm ở chợ, hàng chọn lọc mỗi sáng.",
                   address=f"Ô {10 + i}, {markets[mk].name}", tax_code=f"010{i}2345678", months=6,
                   fee=1000000, docs="", status="active", verified=True,
                   approved_at=datetime.now() - timedelta(days=40))
        db.session.add(st)
        db.session.flush()
        sup = Supplier(stall_id=st.id, name=["HTX Rau Văn Đức", "Trại Thịt Sạch Ba Vì", "Công ty Lương thực Thái Bình"][i],
                       code=f"NCC{i + 1:03d}", phone="0988000000", address="Hà Nội / vùng lân cận")
        db.session.add(sup)
        db.session.flush()
        batch = Batch(stall_id=st.id, supplier_id=sup.id, batch_code=f"LO-2610-{i + 1:03d}",
                      product_name=name, quantity=300, document="Hóa đơn + CO + kiểm dịch",
                      import_date=datetime.now() - timedelta(days=2), verified=True)
        db.session.add(batch)
        db.session.flush()
        for pn, unit, price, stock, w, em in prods:
            db.session.add(Product(stall_id=st.id, category_id=cats[ct].id, batch_id=batch.id, name=pn,
                                   unit=unit, price=price, stock=stock, weight_kg=w, emoji=em,
                                   description=f"{pn} chất lượng, nguồn gốc rõ ràng, có thể truy xuất theo mã lô {batch.batch_code}."))
        stalls.append(st)

    # Một hồ sơ đang chờ BQL kiểm tra để demo luồng 1
    pending = make_user("Chị Thu", "banhang4@cho.vn", "merchant", phone="0903000004")
    db.session.flush()
    db.session.add(Stall(owner_id=pending.id, market_id=markets[2].id, category_id=cats[4].id,
                         name="Thu - Bánh kẹo đặc sản", address="Ô 5, Chợ Nghĩa Tân", tax_code="0109998887",
                         months=3, docs="", status="submitted"))
    db.session.flush()

    # Đơn lịch sử đã hoàn tất để có số liệu doanh thu
    all_products = Product.query.all()
    for n in range(24):
        day = datetime.now() - timedelta(days=random.randint(0, 40), hours=random.randint(0, 8))
        o = Order(customer_id=cust.id, receiver_name=cust.full_name, phone=cust.phone, address=cust.address,
                  district=cust.district, delivery_type=random.choice(["instant", "economy", "pickup"]),
                  payment_method=random.choice(["cod", "bank"]), payment_status="paid", status="completed",
                  created_at=day)
        db.session.add(o)
        db.session.flush()
        o.code = f"DH{day:%y%m%d}{o.id:04d}"
        chosen = random.sample(all_products, random.randint(1, 3))
        by = {}
        for p in chosen:
            by.setdefault(p.stall_id, []).append(p)
        tot = fee_sum = 0
        for i, (sid, ps) in enumerate(by.items(), 1):
            fee = {"pickup": 0, "instant": 25000, "economy": 10000}[o.delivery_type]
            sub = SubOrder(order_id=o.id, stall_id=sid, code=f"{o.code}-{i}", status="completed",
                           shipping_fee=fee, created_at=day, completed_at=day + timedelta(hours=3))
            db.session.add(sub)
            db.session.flush()
            s_total = 0
            for p in ps:
                q = random.randint(1, 3)
                db.session.add(OrderItem(suborder_id=sub.id, product_id=p.id, batch_id=p.batch_id, name=p.name,
                                         unit=p.unit, unit_price=p.price, quantity=q,
                                         batch_code=p.batch.batch_code if p.batch else None))
                s_total += p.price * q
            sub.subtotal = s_total
            tot += s_total
            fee_sum += fee
        o.subtotal, o.shipping_fee, o.total = tot, fee_sum, tot + fee_sum
    db.session.commit()
