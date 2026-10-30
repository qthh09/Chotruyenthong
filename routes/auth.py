from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from helpers import ROLE_HOME, login_required
from models import Notification, User, db

bp = Blueprint("auth", __name__)


@bp.route("/dang-nhap", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password", "")):
            if user.is_locked:
                flash("Tài khoản đã bị khoá. Liên hệ quản trị hệ thống.", "danger")
            else:
                session.clear()
                session["uid"] = user.id
                nxt = request.args.get("next")
                if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                    return redirect(nxt)
                return redirect(url_for(ROLE_HOME.get(user.role, "shop.index")))
        else:
            flash("Email hoặc mật khẩu chưa đúng.", "danger")
    return render_template("login.html")


@bp.route("/dang-ky", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        email = f.get("email", "").strip().lower()
        role = f.get("role", "customer")
        if role not in ("customer", "merchant", "shipper"):
            role = "customer"
        if len(f.get("password", "")) < 6:
            flash("Mật khẩu cần tối thiểu 6 ký tự.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Email này đã được đăng ký.", "danger")
        elif not f.get("full_name", "").strip():
            flash("Vui lòng nhập họ tên.", "danger")
        else:
            u = User(full_name=f["full_name"].strip(), email=email, phone=f.get("phone"),
                     role=role, district=f.get("district") or None, vehicle=f.get("vehicle") or None)
            u.set_password(f["password"])
            db.session.add(u)
            db.session.commit()
            session.clear()
            session["uid"] = u.id
            flash("Đăng ký thành công. Chào mừng bạn đến với chợ số!", "success")
            return redirect(url_for(ROLE_HOME[role]))
    return render_template("register.html")


@bp.route("/dang-xuat")
def logout():
    session.clear()
    return redirect(url_for("shop.index"))


@bp.route("/tai-khoan", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        f = request.form
        g.user.full_name = f.get("full_name", g.user.full_name)
        g.user.phone = f.get("phone")
        g.user.address = f.get("address")
        g.user.district = f.get("district") or None
        if g.user.role == "shipper":
            g.user.vehicle = f.get("vehicle")
        if f.get("new_password"):
            if len(f["new_password"]) < 6:
                flash("Mật khẩu mới cần tối thiểu 6 ký tự.", "danger")
                return redirect(url_for("auth.profile"))
            g.user.set_password(f["new_password"])
        db.session.commit()
        flash("Đã lưu thông tin tài khoản.", "success")
        return redirect(url_for("auth.profile"))
    return render_template("profile.html")


@bp.route("/thong-bao")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.id.desc()).limit(60).all()
    shown = [(n, n.is_read) for n in items]
    for n in items:
        n.is_read = True
    db.session.commit()
    return render_template("notifications.html", items=shown)
