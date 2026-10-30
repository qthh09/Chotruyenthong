from collections import OrderedDict

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   session, url_for)

from helpers import (get_cart, login_required, notify, notify_role, refresh_order_status)
from models import (Batch, Category, Market, Order, OrderItem, Product, Review, Stall, SubOrder,
                    Ticket, db)

bp = Blueprint("shop", __name__)


def active_products():
    return (Product.query.join(Stall, Product.stall_id == Stall.id)
            .filter(Stall.status == "active", Product.is_active.is_(True)))


@bp.route("/")
def index():
    return render_template(
        "index.html", markets=Market.query.all(), cats=Category.query.all(),
        featured=active_products().order_by(Product.id.desc()).limit(8).all(),
        stalls=Stall.query.filter_by(status="active").limit(6).all())


@bp.route("/san-pham")
def products():
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", type=int)
    market = request.args.get("market", type=int)
    sort = request.args.get("sort", "new")
    page = request.args.get("page", 1, type=int)
    query = active_products()
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Product.name.ilike(like), Stall.name.ilike(like)))
    if cat:
        query = query.filter(Product.category_id == cat)
    if market:
        query = query.filter(Stall.market_id == market)
    order = {"price_asc": Product.price.asc(), "price_desc": Product.price.desc()}.get(sort, Product.id.desc())
    pag = query.order_by(order).paginate(page=page, per_page=12, error_out=False)
    return render_template("products.html", pag=pag, q=q, cat=cat, market=market, sort=sort,
                           cats=Category.query.all(), markets=Market.query.all())


@bp.route("/san-pham/<int:pid>")
def product_detail(pid):
    p = db.get_or_404(Product, pid)
    if p.stall.status != "active" or not p.is_active:
        abort(404)
    return render_template("product_detail.html", p=p)


@bp.route("/gian-hang/<int:sid>")
def stall(sid):
    s = db.get_or_404(Stall, sid)
    if s.status != "active":
        abort(404)
    prods = Product.query.filter_by(stall_id=sid, is_active=True).all()
    return render_template("stall.html", s=s, prods=prods)


# ----------------------------------------------------------------- giỏ hàng
def cart_items():
    items, total = [], 0
    cart = get_cart()
    for pid, qty in list(cart.items()):
        p = db.session.get(Product, int(pid))
        if not p or not p.is_active or p.stall.status != "active":
            cart.pop(pid)
            session.modified = True
            continue
        line = p.price * qty
        total += line
        items.append({"product": p, "qty": qty, "line": line})
    return items, total


@bp.route("/gio-hang")
def cart():
    items, total = cart_items()
    groups = OrderedDict()
    for it in items:
        groups.setdefault(it["product"].stall, []).append(it)
    return render_template("cart.html", groups=groups, total=total)


@bp.route("/gio-hang/them", methods=["POST"])
def cart_add():
    pid = request.form.get("product_id", type=int)
    qty = max(1, request.form.get("qty", 1, type=int))
    p = db.get_or_404(Product, pid)
    cart = get_cart()
    new_qty = cart.get(str(pid), 0) + qty
    if new_qty > p.stock:
        flash(f"Gian hàng chỉ còn {p.stock} {p.unit} “{p.name}”.", "warning")
        new_qty = p.stock
    if new_qty > 0:
        cart[str(pid)] = new_qty
        session.modified = True
        flash(f"Đã thêm “{p.name}” vào giỏ hàng.", "success")
    back = request.form.get("back")
    return redirect(back if back and back.startswith("/") and not back.startswith("//") else url_for("shop.cart"))


@bp.route("/gio-hang/cap-nhat", methods=["POST"])
def cart_update():
    cart = get_cart()
    for pid in list(cart):
        qty = request.form.get(f"qty_{pid}", type=int)
        if qty is None:
            continue
        p = db.session.get(Product, int(pid))
        if qty <= 0:
            cart.pop(pid)
        else:
            cart[pid] = min(qty, p.stock) if p else qty
    session.modified = True
    return redirect(url_for("shop.cart"))


@bp.route("/gio-hang/xoa/<int:pid>", methods=["POST"])
def cart_remove(pid):
    get_cart().pop(str(pid), None)
    session.modified = True
    return redirect(url_for("shop.cart"))


# ---------------------------------------------------------------- đặt hàng
def ship_fee_for(delivery_type):
    return {"pickup": 0, "instant": current_app.config["SHIP_FEE_INSTANT"],
            "economy": current_app.config["SHIP_FEE_ECONOMY"]}[delivery_type]


@bp.route("/dat-hang", methods=["GET", "POST"])
@login_required
def checkout():
    items, total = cart_items()
    if not items:
        flash("Giỏ hàng đang trống.", "info")
        return redirect(url_for("shop.products"))
    if g.user.role != "customer":
        flash("Chỉ tài khoản khách hàng mới đặt hàng được.", "warning")
        return redirect(url_for("shop.cart"))
    stalls = {it["product"].stall_id for it in items}
    if request.method == "POST":
        f = request.form
        dtype = f.get("delivery_type", "instant")
        pay = f.get("payment_method", "cod")
        if dtype not in ("pickup", "instant", "economy") or pay not in ("cod", "bank", "wallet"):
            abort(400)
        if dtype != "pickup" and not (f.get("address") and f.get("district") and f.get("phone")):
            flash("Vui lòng nhập đầy đủ số điện thoại, quận/huyện và địa chỉ giao hàng.", "danger")
            return redirect(url_for("shop.checkout"))
        for it in items:
            if it["qty"] > it["product"].stock:
                flash(f"“{it['product'].name}” chỉ còn {it['product'].stock} {it['product'].unit}.", "danger")
                return redirect(url_for("shop.cart"))
        order = Order(
            customer_id=g.user.id, receiver_name=f.get("receiver_name") or g.user.full_name,
            phone=f.get("phone"), address=f.get("address") or "Nhận tại chợ",
            district=f.get("district") or "", note=f.get("note"), delivery_type=dtype,
            time_window=f.get("time_window") if dtype == "economy" else None,
            payment_method=pay, payment_status="pending")
        db.session.add(order)
        db.session.flush()
        order.code = f"DH{order.created_at:%y%m%d}{order.id:04d}"
        fee = ship_fee_for(dtype)
        sub_total = 0
        by_stall = OrderedDict()
        for it in items:
            by_stall.setdefault(it["product"].stall_id, []).append(it)
        for i, (sid, its) in enumerate(by_stall.items(), 1):
            sub = SubOrder(order_id=order.id, stall_id=sid, shipping_fee=fee,
                           code=f"{order.code}-{i}",
                           status="new" if pay == "cod" else "pending_payment")
            db.session.add(sub)
            db.session.flush()
            s_total = 0
            for it in its:
                p = it["product"]
                p.stock -= it["qty"]
                db.session.add(OrderItem(
                    suborder_id=sub.id, product_id=p.id, batch_id=p.batch_id, name=p.name,
                    unit=p.unit, unit_price=p.price, quantity=it["qty"],
                    batch_code=p.batch.batch_code if p.batch else None))
                s_total += it["line"]
            sub.subtotal = s_total
            sub_total += s_total
            if pay == "cod":
                notify(sub.stall.owner_id, f"Đơn mới {sub.code} từ {order.receiver_name}",
                       url_for("merchant.order_detail", sid=sub.id))
        order.subtotal = sub_total
        order.shipping_fee = fee * len(by_stall)
        order.total = order.subtotal + order.shipping_fee
        refresh_order_status(order)
        db.session.commit()
        session["cart"] = {}
        if pay == "cod":
            flash("Đặt hàng thành công! Các gian hàng đã nhận được thông báo.", "success")
            return redirect(url_for("shop.order_detail", oid=order.id))
        return redirect(url_for("shop.pay", oid=order.id))
    return render_template("checkout.html", items=items, total=total, n_stalls=len(stalls),
                           fees={"pickup": 0, "instant": ship_fee_for("instant"),
                                 "economy": ship_fee_for("economy")})


@bp.route("/don-hang/<int:oid>/thanh-toan", methods=["GET", "POST"])
@login_required
def pay(oid):
    o = db.get_or_404(Order, oid)
    if o.customer_id != g.user.id:
        abort(403)
    if o.payment_status == "paid" or o.payment_method == "cod" or o.status == "cancelled":
        return redirect(url_for("shop.order_detail", oid=o.id))
    if request.method == "POST":
        if request.form.get("result") == "success":
            o.payment_status = "paid"
            for s in o.suborders:
                if s.status == "pending_payment":
                    s.status = "new"
                    notify(s.stall.owner_id, f"Đơn mới {s.code} (đã thanh toán online)",
                           url_for("merchant.order_detail", sid=s.id))
            refresh_order_status(o)
            db.session.commit()
            flash("Thanh toán thành công. Đơn hàng đã được gửi tới các gian hàng.", "success")
            return redirect(url_for("shop.order_detail", oid=o.id))
        o.payment_status = "failed"
        db.session.commit()
        flash("Thanh toán chưa thành công. Bạn có thể thử lại hoặc huỷ đơn.", "danger")
    return render_template("pay.html", o=o)


@bp.route("/don-hang")
@login_required
def orders():
    items = Order.query.filter_by(customer_id=g.user.id).order_by(Order.id.desc()).all()
    return render_template("orders.html", items=items)


@bp.route("/don-hang/<int:oid>")
@login_required
def order_detail(oid):
    o = db.get_or_404(Order, oid)
    if o.customer_id != g.user.id and g.user.role not in ("admin", "bql"):
        abort(403)
    return render_template("order_detail.html", o=o)


@bp.route("/don-hang/<int:oid>/huy", methods=["POST"])
@login_required
def order_cancel(oid):
    o = db.get_or_404(Order, oid)
    if o.customer_id != g.user.id:
        abort(403)
    if any(s.status not in ("new", "pending_payment") for s in o.suborders):
        flash("Đơn đã được gian hàng xử lý nên không thể tự huỷ. Hãy gửi khiếu nại/hỗ trợ.", "warning")
    else:
        for s in o.suborders:
            for it in s.items:
                if it.product:
                    it.product.stock += it.quantity
            s.status = "cancelled"
            notify(s.stall.owner_id, f"Khách đã huỷ đơn {s.code}")
        refresh_order_status(o)
        db.session.commit()
        flash("Đã huỷ đơn hàng.", "success")
    return redirect(url_for("shop.order_detail", oid=oid))


@bp.route("/danh-gia/<int:item_id>", methods=["POST"])
@login_required
def review(item_id):
    it = db.get_or_404(OrderItem, item_id)
    if it.suborder.order.customer_id != g.user.id or it.suborder.status != "completed":
        abort(403)
    if not Review.query.filter_by(item_id=item_id).first() and it.product_id:
        db.session.add(Review(product_id=it.product_id, user_id=g.user.id, item_id=item_id,
                              rating=min(5, max(1, request.form.get("rating", 5, type=int))),
                              comment=request.form.get("comment", "").strip()))
        db.session.commit()
        flash("Cảm ơn bạn đã đánh giá sản phẩm.", "success")
    return redirect(url_for("shop.order_detail", oid=it.suborder.order_id))


@bp.route("/ho-tro", methods=["POST"])
@login_required
def ticket():
    content = request.form.get("content", "").strip()
    if content:
        db.session.add(Ticket(user_id=g.user.id, order_id=request.form.get("order_id", type=int),
                              content=content))
        notify_role("admin", f"Khiếu nại/hỗ trợ mới từ {g.user.full_name}", url_for("admin.tickets"))
        notify_role("bql", f"Khiếu nại/hỗ trợ mới từ {g.user.full_name}", url_for("admin.tickets"))
        db.session.commit()
        flash("Đã gửi yêu cầu. Chúng tôi sẽ phản hồi sớm.", "success")
    return redirect(request.referrer or url_for("shop.orders"))


# ------------------------------------------------------- truy xuất nguồn gốc
@bp.route("/truy-xuat")
def trace():
    code = request.args.get("code", "").strip()
    batch = affected = None
    products = []
    if code:
        batch = Batch.query.filter(db.func.lower(Batch.batch_code) == code.lower()).first()
        if batch:
            products = Product.query.filter_by(batch_id=batch.id).all()
            if g.user and g.user.role in ("admin", "bql"):
                affected = OrderItem.query.filter_by(batch_id=batch.id).order_by(OrderItem.id.desc()).all()
        else:
            flash("Không tìm thấy mã lô này.", "warning")
    return render_template("trace.html", code=code, batch=batch, affected=affected, products=products)
