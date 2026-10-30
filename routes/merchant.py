import os
import uuid
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

from helpers import (calc_stall_fee, notify, notify_role, refresh_order_status, revenue_series,
                     roles_required)
from models import (Batch, Category, DeliveryRequest, Market, Product, Stall, SubOrder, Supplier, db)

bp = Blueprint("merchant", __name__, url_prefix="/merchant")


def my_stall():
    return g.user.stall


def active_stall_required():
    s = my_stall()
    if not s or s.status != "active":
        flash("Gian hàng chưa được kích hoạt. Hãy hoàn tất đăng ký gian hàng số trước.", "warning")
        return None
    return s


@bp.route("/")
@roles_required("merchant")
def dashboard():
    s = my_stall()
    stats = None
    if s and s.status == "active":
        stats = revenue_series(s.id)
        stats["new_orders"] = SubOrder.query.filter_by(stall_id=s.id, status="new").count()
        stats["processing"] = SubOrder.query.filter(
            SubOrder.stall_id == s.id,
            SubOrder.status.in_(["accepted", "preparing", "ready", "ship_requested", "handed_over", "delivering"])).count()
        stats["products"] = Product.query.filter_by(stall_id=s.id).count()
        stats["low_stock"] = Product.query.filter(Product.stall_id == s.id, Product.stock <= 5).all()
    return render_template("merchant/dashboard.html", s=s, stats=stats)


# ------------------------------------------------ Luồng 1: đăng ký gian hàng số
@bp.route("/gian-hang", methods=["GET", "POST"])
@roles_required("merchant")
def stall_form():
    s = my_stall()
    if s and s.status not in ("draft", "need_more"):
        return redirect(url_for("merchant.dashboard"))
    if request.method == "POST":
        f = request.form
        if not f.get("name") or not f.get("market_id") or not f.get("category_id"):
            flash("Vui lòng nhập tên gian hàng, chợ và nhóm ngành hàng.", "danger")
            return redirect(url_for("merchant.stall_form"))
        if not s:
            s = Stall(owner_id=g.user.id, name=f["name"])
            db.session.add(s)
        s.name = f["name"]
        s.market_id = int(f["market_id"])
        s.category_id = int(f["category_id"])
        s.address = f.get("address")
        s.description = f.get("description")
        s.tax_code = f.get("tax_code")
        s.months = int(f.get("months", 3))
        saved = [x for x in (s.docs or "").split(",") if x]
        for file in request.files.getlist("docs"):
            if not file or not file.filename:
                continue
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
                flash(f"Tệp “{file.filename}” không hợp lệ (chỉ nhận PNG, JPG, PDF).", "danger")
                return redirect(url_for("merchant.stall_form"))
            name = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
            file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))
            saved.append(name)
        if not saved:
            flash("Vui lòng tải lên ít nhất một giấy tờ/hình ảnh minh chứng.", "danger")
            db.session.rollback()
            return redirect(url_for("merchant.stall_form"))
        s.docs = ",".join(saved)
        s.status = "submitted"
        s.bql_note = None
        notify_role("bql", f"Hồ sơ gian hàng “{s.name}” cần kiểm tra", url_for("bql.dashboard"))
        db.session.commit()
        flash("Đã gửi hồ sơ cho Ban quản lý chợ kiểm tra.", "success")
        return redirect(url_for("merchant.dashboard"))
    return render_template("merchant/stall_form.html", s=s, markets=Market.query.all(),
                           cats=Category.query.all())


@bp.route("/gian-hang/thanh-toan", methods=["GET", "POST"])
@roles_required("merchant")
def pay_fee():
    s = my_stall()
    if not s or s.status != "awaiting_payment":
        return redirect(url_for("merchant.dashboard"))
    if request.method == "POST":
        s.status = "paid"
        s.paid_at = datetime.now()
        notify_role("bql", f"Gian hàng “{s.name}” đã thanh toán phí, chờ phê duyệt", url_for("bql.dashboard"))
        db.session.commit()
        flash("Thanh toán phí thành công. Hồ sơ đang chờ Ban quản lý chợ phê duyệt.", "success")
        return redirect(url_for("merchant.dashboard"))
    return render_template("merchant/pay_fee.html", s=s)


@bp.route("/tai-lieu/<path:name>")
@roles_required("merchant", "bql")
def doc(name):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], name)


# --------------------------------------------------- Sản phẩm / giá / tồn kho
@bp.route("/san-pham")
@roles_required("merchant")
def products():
    s = active_stall_required()
    if not s:
        return redirect(url_for("merchant.dashboard"))
    return render_template("merchant/products.html", s=s,
                           items=Product.query.filter_by(stall_id=s.id).order_by(Product.id.desc()).all())


@bp.route("/san-pham/moi", methods=["GET", "POST"])
@bp.route("/san-pham/<int:pid>", methods=["GET", "POST"])
@roles_required("merchant")
def product_form(pid=None):
    s = active_stall_required()
    if not s:
        return redirect(url_for("merchant.dashboard"))
    p = db.get_or_404(Product, pid) if pid else None
    if p and p.stall_id != s.id:
        abort(403)
    if request.method == "POST":
        f = request.form
        try:
            price, stock = int(f["price"]), int(f["stock"])
            weight = float(f.get("weight_kg") or 1)
        except (KeyError, ValueError):
            flash("Giá, số lượng và khối lượng phải là số.", "danger")
            return redirect(request.url)
        if price < 0 or stock < 0:
            flash("Giá và số lượng không được âm.", "danger")
            return redirect(request.url)
        if not p:
            p = Product(stall_id=s.id)
            db.session.add(p)
        p.name = f["name"].strip()
        p.description = f.get("description")
        p.unit = f.get("unit", "kg")
        p.price, p.stock, p.weight_kg = price, stock, weight
        p.emoji = f.get("emoji") or "🥬"
        p.category_id = int(f.get("category_id") or s.category_id)
        p.batch_id = int(f["batch_id"]) if f.get("batch_id") else None
        p.is_active = bool(f.get("is_active"))
        db.session.commit()
        flash("Đã lưu sản phẩm.", "success")
        return redirect(url_for("merchant.products"))
    return render_template("merchant/product_form.html", p=p, s=s, cats=Category.query.all(),
                           batches=Batch.query.filter_by(stall_id=s.id).all())


@bp.route("/san-pham/<int:pid>/kho", methods=["POST"])
@roles_required("merchant")
def quick_update(pid):
    p = db.get_or_404(Product, pid)
    if p.stall_id != my_stall().id:
        abort(403)
    p.stock = max(0, request.form.get("stock", p.stock, type=int))
    p.price = max(0, request.form.get("price", p.price, type=int))
    db.session.commit()
    flash(f"Đã cập nhật giá và tồn kho “{p.name}”.", "success")
    return redirect(url_for("merchant.products"))


# ---------------------------------------------------- Truy xuất: NCC + lô hàng
@bp.route("/nguon-goc", methods=["GET", "POST"])
@roles_required("merchant")
def traceability():
    s = active_stall_required()
    if not s:
        return redirect(url_for("merchant.dashboard"))
    if request.method == "POST":
        f = request.form
        if f.get("kind") == "supplier":
            db.session.add(Supplier(stall_id=s.id, name=f["name"], code=f.get("code"),
                                    phone=f.get("phone"), address=f.get("address")))
            flash("Đã thêm nhà cung cấp.", "success")
        elif f.get("kind") == "batch":
            code = f["batch_code"].strip().upper()
            if Batch.query.filter_by(batch_code=code).first():
                flash("Mã lô này đã tồn tại.", "danger")
                return redirect(url_for("merchant.traceability"))
            db.session.add(Batch(stall_id=s.id, supplier_id=int(f["supplier_id"]), batch_code=code,
                                 product_name=f.get("product_name"), quantity=int(f.get("quantity") or 0),
                                 document=f.get("document")))
            notify_role("bql", f"Lô hàng {code} của “{s.name}” chờ xác minh", url_for("bql.dashboard"))
            flash("Đã ghi nhận lô hàng. Ban quản lý chợ sẽ xác minh chứng từ.", "success")
        db.session.commit()
        return redirect(url_for("merchant.traceability"))
    return render_template("merchant/traceability.html", s=s, suppliers=Supplier.query.filter_by(stall_id=s.id).all(),
                           batches=Batch.query.filter_by(stall_id=s.id).order_by(Batch.id.desc()).all())


# -------------------------------------------------- Luồng 3: xử lý đơn hàng
def own_suborder(sid):
    sub = db.get_or_404(SubOrder, sid)
    if not my_stall() or sub.stall_id != my_stall().id:
        abort(403)
    return sub


@bp.route("/don-hang")
@roles_required("merchant")
def orders():
    s = active_stall_required()
    if not s:
        return redirect(url_for("merchant.dashboard"))
    status = request.args.get("status")
    q = SubOrder.query.filter(SubOrder.stall_id == s.id, SubOrder.status != "pending_payment")
    if status:
        q = q.filter(SubOrder.status == status)
    return render_template("merchant/orders.html", items=q.order_by(SubOrder.id.desc()).all(), status=status)


@bp.route("/don-hang/<int:sid>")
@roles_required("merchant")
def order_detail(sid):
    return render_template("merchant/order_detail.html", s=own_suborder(sid))


@bp.route("/don-hang/<int:sid>/thao-tac", methods=["POST"])
@roles_required("merchant")
def order_action(sid):
    sub = own_suborder(sid)
    order = sub.order
    act = request.form.get("action")
    st = sub.status
    link = url_for("shop.order_detail", oid=order.id)

    if act == "accept" and st == "new":
        sub.status = "accepted"
        notify(order.customer_id, f"Gian hàng {sub.stall.name} đã xác nhận đơn {sub.code}", link)
    elif act == "reject" and st == "new":
        sub.status = "rejected"
        sub.reject_reason = request.form.get("reason") or "Hết hàng"
        for it in sub.items:
            if it.product:
                it.product.stock += it.quantity
        notify(order.customer_id, f"Gian hàng {sub.stall.name} từ chối đơn {sub.code}: {sub.reject_reason}", link)
    elif act == "prepare" and st == "accepted":
        sub.status = "preparing"
    elif act == "ready" and st == "preparing":
        sub.status = "ready"
        notify(order.customer_id, f"Hàng của đơn {sub.code} đã chuẩn bị xong", link)
    elif act == "pickup_done" and st == "ready" and order.delivery_type == "pickup":
        sub.status, sub.completed_at = "completed", datetime.now()
        notify(order.customer_id, f"Bạn đã nhận hàng đơn {sub.code}. Hãy đánh giá sản phẩm nhé!", link)
    elif act == "request_ship" and st == "ready" and order.delivery_type in ("instant", "economy"):
        handling = "fresh" if any(i.product and i.product.category and i.product.category.handling == "fresh"
                                  for i in sub.items) else "dry"
        weight = sum((i.product.weight_kg if i.product else 1) * i.quantity for i in sub.items)
        db.session.add(DeliveryRequest(
            suborder_id=sub.id, type=order.delivery_type, fee=sub.shipping_fee,
            status="pending" if order.delivery_type == "instant" else "waiting_batch",
            district=order.district, window=order.time_window, handling=handling, weight=weight))
        sub.status = "ship_requested"
        notify_role("operator", f"Yêu cầu giao {order.delivery_type} mới từ {sub.stall.name}", url_for("ops.dispatch"))
    elif act == "handover" and st == "ship_requested" and sub.delivery and sub.delivery.status == "assigned":
        sub.status = "handed_over"
        sub.delivery.status = "picked"
        notify(sub.delivery.shipper_id, f"{sub.stall.name} đã bàn giao đơn {sub.code}", url_for("ops.shipper"))
        notify(order.customer_id, f"Đơn {sub.code} đã giao cho shipper", link)
    else:
        flash("Thao tác không hợp lệ ở trạng thái hiện tại.", "warning")
        return redirect(url_for("merchant.order_detail", sid=sid))
    refresh_order_status(order)
    db.session.commit()
    flash("Đã cập nhật trạng thái đơn hàng.", "success")
    return redirect(url_for("merchant.order_detail", sid=sid))
