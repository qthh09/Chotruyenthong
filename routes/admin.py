from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from helpers import ROLE_LABEL, notify, revenue_series, roles_required
from models import (Category, Market, Order, Product, Stall, SubOrder, Ticket, User, db)

bp = Blueprint("admin", __name__, url_prefix="/quan-tri")


@bp.route("/")
@roles_required("admin")
def dashboard():
    stats = revenue_series()
    counts = {
        "users": User.query.count(), "stalls": Stall.query.filter_by(status="active").count(),
        "products": Product.query.count(), "orders": Order.query.count(),
        "open_tickets": Ticket.query.filter_by(status="open").count(),
    }
    top = {}
    for s in SubOrder.query.filter_by(status="completed").all():
        top[s.stall.name] = top.get(s.stall.name, 0) + s.subtotal
    top = sorted(top.items(), key=lambda x: -x[1])[:5]
    return render_template("admin/dashboard.html", stats=stats, counts=counts, top=top)


@bp.route("/nguoi-dung", methods=["GET", "POST"])
@roles_required("admin")
def users():
    if request.method == "POST":
        u = db.get_or_404(User, request.form.get("user_id", type=int))
        if u.id == g.user.id:
            flash("Không thể thay đổi chính tài khoản đang đăng nhập.", "warning")
        else:
            if request.form.get("role") in ROLE_LABEL:
                u.role = request.form["role"]
            if request.form.get("toggle_lock"):
                u.is_locked = not u.is_locked
            db.session.commit()
            flash("Đã cập nhật người dùng.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/users.html", items=User.query.order_by(User.id).all(), roles=ROLE_LABEL)


@bp.route("/cho-nganh-hang", methods=["GET", "POST"])
@roles_required("admin")
def markets():
    if request.method == "POST":
        f = request.form
        if f.get("kind") == "market" and f.get("name"):
            db.session.add(Market(name=f["name"], address=f.get("address"), district=f.get("district")))
        elif f.get("kind") == "category" and f.get("name"):
            db.session.add(Category(name=f["name"], emoji=f.get("emoji") or "🛒",
                                    fee_per_month=int(f.get("fee_per_month") or 200000),
                                    handling=f.get("handling", "general")))
        db.session.commit()
        flash("Đã lưu.", "success")
        return redirect(url_for("admin.markets"))
    return render_template("admin/markets.html", markets=Market.query.all(), cats=Category.query.all())


@bp.route("/ho-tro", methods=["GET", "POST"])
@roles_required("admin", "bql")
def tickets():
    if request.method == "POST":
        t = db.get_or_404(Ticket, request.form.get("ticket_id", type=int))
        t.reply = request.form.get("reply", "").strip()
        t.status = "closed" if t.reply else "open"
        notify(t.user_id, "Yêu cầu hỗ trợ của bạn đã có phản hồi", url_for("shop.orders"))
        db.session.commit()
        flash("Đã phản hồi.", "success")
        return redirect(url_for("admin.tickets"))
    return render_template("admin/tickets.html", items=Ticket.query.order_by(Ticket.id.desc()).all())
