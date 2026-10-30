from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Người dùng: customer, merchant, shipper, bql, operator, admin."""
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    is_locked = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(255))
    district = db.Column(db.String(60))
    vehicle = db.Column(db.String(60))          # shipper
    is_available = db.Column(db.Boolean, default=True)  # shipper
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Market(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    district = db.Column(db.String(60))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    emoji = db.Column(db.String(8), default="🛒")
    fee_per_month = db.Column(db.Integer, default=200000)
    handling = db.Column(db.String(20), default="general")  # fresh | dry | general


class Stall(db.Model):
    """Gian hàng số. status: draft, submitted, need_more, awaiting_payment, paid, active, rejected."""
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    market_id = db.Column(db.Integer, db.ForeignKey("market.id"))
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    address = db.Column(db.String(255))
    tax_code = db.Column(db.String(30))
    months = db.Column(db.Integer, default=3)
    fee = db.Column(db.Integer, default=0)
    docs = db.Column(db.String(500), default="")
    status = db.Column(db.String(20), default="draft")
    bql_note = db.Column(db.Text)
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    paid_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)

    owner = db.relationship("User", backref=db.backref("stall", uselist=False))
    market = db.relationship("Market")
    category = db.relationship("Category")


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stall_id = db.Column(db.Integer, db.ForeignKey("stall.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(40))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    stall = db.relationship("Stall", backref="suppliers")


class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stall_id = db.Column(db.Integer, db.ForeignKey("stall.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False)
    batch_code = db.Column(db.String(40), unique=True, nullable=False)
    product_name = db.Column(db.String(150))
    import_date = db.Column(db.DateTime, default=datetime.now)
    quantity = db.Column(db.Integer, default=0)
    document = db.Column(db.String(200))   # hóa đơn, CO, chứng từ
    verified = db.Column(db.Boolean, default=False)

    stall = db.relationship("Stall", backref="batches")
    supplier = db.relationship("Supplier", backref="batches")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stall_id = db.Column(db.Integer, db.ForeignKey("stall.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"))
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    unit = db.Column(db.String(20), default="kg")
    price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, default=0)
    weight_kg = db.Column(db.Float, default=1.0)
    emoji = db.Column(db.String(8), default="🥬")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    stall = db.relationship("Stall", backref="products")
    category = db.relationship("Category")
    batch = db.relationship("Batch")

    @property
    def avg_rating(self):
        rs = [r.rating for r in self.reviews]
        return round(sum(rs) / len(rs), 1) if rs else None


class Order(db.Model):
    """Đơn của khách hàng (có thể tách thành nhiều SubOrder theo Merchant)."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_name = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    district = db.Column(db.String(60))
    note = db.Column(db.Text)
    delivery_type = db.Column(db.String(20), default="instant")  # pickup | instant | economy
    time_window = db.Column(db.String(40))
    payment_method = db.Column(db.String(20), default="cod")     # cod | bank | wallet
    payment_status = db.Column(db.String(20), default="pending") # pending | paid | failed
    subtotal = db.Column(db.Integer, default=0)
    shipping_fee = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="processing")
    created_at = db.Column(db.DateTime, default=datetime.now)

    customer = db.relationship("User", backref="orders")


class SubOrder(db.Model):
    """Đơn của từng Merchant."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    stall_id = db.Column(db.Integer, db.ForeignKey("stall.id"), nullable=False)
    status = db.Column(db.String(20), default="new")
    subtotal = db.Column(db.Integer, default=0)
    shipping_fee = db.Column(db.Integer, default=0)
    reject_reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime)

    order = db.relationship("Order", backref=db.backref("suborders", order_by="SubOrder.id"))
    stall = db.relationship("Stall", backref="suborders")

    @property
    def total(self):
        return (self.subtotal or 0) + (self.shipping_fee or 0)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    suborder_id = db.Column(db.Integer, db.ForeignKey("sub_order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"))
    name = db.Column(db.String(150))
    unit = db.Column(db.String(20))
    unit_price = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    batch_code = db.Column(db.String(40))

    suborder = db.relationship("SubOrder", backref="items")
    product = db.relationship("Product")

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class DeliveryTrip(db.Model):
    """Chuyến giao tiết kiệm (gom nhiều đơn)."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30))
    shipper_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    district = db.Column(db.String(60))
    window = db.Column(db.String(40))
    handling = db.Column(db.String(20))
    status = db.Column(db.String(20), default="assigned")  # assigned | done
    created_at = db.Column(db.DateTime, default=datetime.now)

    shipper = db.relationship("User")


class DeliveryRequest(db.Model):
    """pending (giao ngay, chờ shipper) | waiting_batch | assigned | picked | delivering | delivered"""
    id = db.Column(db.Integer, primary_key=True)
    suborder_id = db.Column(db.Integer, db.ForeignKey("sub_order.id"), unique=True, nullable=False)
    type = db.Column(db.String(20))   # instant | economy
    status = db.Column(db.String(20), default="pending")
    fee = db.Column(db.Integer, default=0)
    district = db.Column(db.String(60))
    window = db.Column(db.String(40))
    handling = db.Column(db.String(20), default="general")
    weight = db.Column(db.Float, default=1.0)
    shipper_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    trip_id = db.Column(db.Integer, db.ForeignKey("delivery_trip.id"))
    route_order = db.Column(db.Integer, default=0)
    cod_amount = db.Column(db.Integer, default=0)
    cod_reconciled = db.Column(db.Boolean, default=False)
    requested_at = db.Column(db.DateTime, default=datetime.now)

    suborder = db.relationship("SubOrder", backref=db.backref("delivery", uselist=False))
    shipper = db.relationship("User")
    trip = db.relationship("DeliveryTrip", backref="requests")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.String(255))
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("order_item.id"), unique=True)
    rating = db.Column(db.Integer, default=5)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    product = db.relationship("Product", backref="reviews")
    user = db.relationship("User")


class Ticket(db.Model):
    """Khiếu nại / hỗ trợ."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))
    content = db.Column(db.Text, nullable=False)
    reply = db.Column(db.Text)
    status = db.Column(db.String(20), default="open")
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User")
    order = db.relationship("Order")
