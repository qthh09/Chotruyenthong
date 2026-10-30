from collections import defaultdict
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from helpers import notify, refresh_order_status, roles_required
from models import DeliveryRequest, DeliveryTrip, User, db

bp = Blueprint("ops", __name__, url_prefix="/van-hanh")

ACTIVE = ("assigned", "picked", "delivering")


def pick_shipper(district):
    """Shipper gần nhất: ưu tiên cùng quận, sau đó ít đơn đang giao nhất."""
    best, best_key = None, None
    for u in User.query.filter_by(role="shipper", is_available=True, is_locked=False).all():
        load = DeliveryRequest.query.filter(DeliveryRequest.shipper_id == u.id,
                                            DeliveryRequest.status.in_(ACTIVE)).count()
        key = (0 if u.district == district else 1, load)
        if best is None or key < best_key:
            best, best_key = u, key
    return best


# ------------------------------------------------ Luồng 4: điều phối (Operator)
@bp.route("/dieu-phoi")
@roles_required("operator")
def dispatch():
    waiting = DeliveryRequest.query.filter_by(status="waiting_batch").all()
    groups = defaultdict(list)
    for r in waiting:
        groups[(r.district, r.window, r.handling)].append(r)
    shippers = []
    for u in User.query.filter_by(role="shipper").all():
        load = DeliveryRequest.query.filter(DeliveryRequest.shipper_id == u.id,
                                            DeliveryRequest.status.in_(ACTIVE)).count()
        shippers.append((u, load))
    return render_template(
        "ops/dispatch.html",
        instant=DeliveryRequest.query.filter_by(status="pending").all(), groups=groups,
        trips=DeliveryTrip.query.order_by(DeliveryTrip.id.desc()).limit(15).all(),
        shippers=shippers,
        cod=DeliveryRequest.query.filter(DeliveryRequest.cod_amount > 0, DeliveryRequest.cod_reconciled.is_(False)).all(),
        recent_active=DeliveryRequest.query.filter(DeliveryRequest.status.in_(ACTIVE)).all())


@bp.route("/giao-ngay/<int:rid>", methods=["POST"])
@roles_required("operator")
def assign_instant(rid):
    r = db.get_or_404(DeliveryRequest, rid)
    if r.status != "pending":
        abort(400)
    sid = request.form.get("shipper_id", type=int)
    shipper = db.session.get(User, sid) if sid else pick_shipper(r.suborder.stall.market.district)
    if not shipper:
        flash("Hiện chưa có shipper nào sẵn sàng.", "danger")
        return redirect(url_for("ops.dispatch"))
    r.shipper_id, r.status = shipper.id, "assigned"
    notify(shipper.id, f"Chuyến giao ngay: lấy hàng tại {r.suborder.stall.name}", url_for("ops.shipper"))
    notify(r.suborder.stall.owner_id, f"Shipper {shipper.full_name} sẽ đến lấy đơn {r.suborder.code}",
           url_for("merchant.order_detail", sid=r.suborder_id))
    db.session.commit()
    flash(f"Đã giao cho shipper {shipper.full_name}.", "success")
    return redirect(url_for("ops.dispatch"))


@bp.route("/gom-don", methods=["POST"])
@roles_required("operator")
def batch_orders():
    """Gom đơn: cùng khu vực, cùng khung giờ, hàng tương thích, phù hợp tải trọng."""
    cfg = current_app.config
    waiting = DeliveryRequest.query.filter_by(status="waiting_batch").all()
    groups = defaultdict(list)
    for r in waiting:
        groups[(r.district, r.window, r.handling)].append(r)
    trips = skipped = 0

    def flush(key, chunk):
        nonlocal trips, skipped
        shipper = pick_shipper(key[0])
        if not shipper:
            skipped += len(chunk)
            return
        trip = DeliveryTrip(shipper_id=shipper.id, district=key[0], window=key[1], handling=key[2])
        db.session.add(trip)
        db.session.flush()
        trip.code = f"CG{datetime.now():%y%m%d}{trip.id:03d}"
        # Tối ưu tuyến (đơn giản): nhóm theo gian hàng lấy hàng, rồi theo địa chỉ giao
        chunk.sort(key=lambda r: (r.suborder.stall_id, r.suborder.order.address))
        for i, r in enumerate(chunk, 1):
            r.trip_id, r.shipper_id, r.status, r.route_order = trip.id, shipper.id, "assigned", i
            notify(r.suborder.stall.owner_id, f"Đơn {r.suborder.code} đã được gom vào chuyến {trip.code}",
                   url_for("merchant.order_detail", sid=r.suborder_id))
        notify(shipper.id, f"Chuyến gom {trip.code}: {len(chunk)} đơn, khu vực {key[0]}", url_for("ops.shipper"))
        trips += 1

    for key, reqs in groups.items():
        chunk, load = [], 0.0
        for r in sorted(reqs, key=lambda r: r.id):
            if chunk and (load + r.weight > cfg["MAX_LOAD_KG"] or len(chunk) >= cfg["MAX_STOPS"]):
                flush(key, chunk)
                chunk, load = [], 0.0
            chunk.append(r)
            load += r.weight
        if chunk:
            flush(key, chunk)
    db.session.commit()
    if skipped:
        flash(f"Đã tạo {trips} chuyến. {skipped} đơn chưa gom được vì không có shipper sẵn sàng.", "warning")
    elif trips:
        flash(f"Đã gom đơn và tạo {trips} chuyến giao tiết kiệm.", "success")
    else:
        flash("Chưa có đơn nào chờ gom.", "info")
    return redirect(url_for("ops.dispatch"))


@bp.route("/doi-soat/<int:rid>", methods=["POST"])
@roles_required("operator")
def reconcile(rid):
    r = db.get_or_404(DeliveryRequest, rid)
    r.cod_reconciled = True
    notify(r.shipper_id, f"Đã đối soát COD đơn {r.suborder.code}")
    db.session.commit()
    flash("Đã đối soát COD.", "success")
    return redirect(url_for("ops.dispatch"))


# ------------------------------------------------------------ Shipper địa phương
@bp.route("/shipper")
@roles_required("shipper")
def shipper():
    mine = DeliveryRequest.query.filter(DeliveryRequest.shipper_id == g.user.id,
                                        DeliveryRequest.status.in_(ACTIVE)) \
        .order_by(DeliveryRequest.trip_id, DeliveryRequest.route_order).all()
    done = DeliveryRequest.query.filter_by(shipper_id=g.user.id, status="delivered") \
        .order_by(DeliveryRequest.id.desc()).limit(10).all()
    cod_hold = sum(r.cod_amount for r in done if not r.cod_reconciled)
    return render_template("ops/shipper.html", mine=mine, done=done, cod_hold=cod_hold)


@bp.route("/shipper/trang-thai", methods=["POST"])
@roles_required("shipper")
def toggle():
    g.user.is_available = not g.user.is_available
    db.session.commit()
    return redirect(url_for("ops.shipper"))


@bp.route("/giao-hang/<int:rid>/<act>", methods=["POST"])
@roles_required("shipper")
def delivery_action(rid, act):
    r = db.get_or_404(DeliveryRequest, rid)
    if r.shipper_id != g.user.id:
        abort(403)
    sub, order = r.suborder, r.suborder.order
    link = url_for("shop.order_detail", oid=order.id)
    if act == "start" and r.status == "picked":
        r.status, sub.status = "delivering", "delivering"
        notify(order.customer_id, f"Đơn {sub.code} đang trên đường giao tới bạn", link)
    elif act == "done" and r.status == "delivering":
        r.status, sub.status, sub.completed_at = "delivered", "completed", datetime.now()
        if order.payment_method == "cod":
            r.cod_amount = sub.total
        notify(order.customer_id, f"Đơn {sub.code} đã giao thành công. Hãy đánh giá sản phẩm nhé!", link)
        notify(sub.stall.owner_id, f"Đơn {sub.code} đã giao thành công", url_for("merchant.order_detail", sid=sub.id))
        if r.trip and all(x.status == "delivered" for x in r.trip.requests):
            r.trip.status = "done"
        refresh_order_status(order)
    else:
        flash("Thao tác không hợp lệ. Hãy chờ Merchant bàn giao hàng trước khi giao.", "warning")
        return redirect(url_for("ops.shipper"))
    db.session.commit()
    return redirect(url_for("ops.shipper"))
