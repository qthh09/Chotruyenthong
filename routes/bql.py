from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from helpers import calc_stall_fee, notify, roles_required
from models import Batch, Stall, db

bp = Blueprint("bql", __name__, url_prefix="/bql")


@bp.route("/")
@roles_required("bql")
def dashboard():
    return render_template(
        "bql/dashboard.html",
        to_check=Stall.query.filter_by(status="submitted").all(),
        to_approve=Stall.query.filter_by(status="paid").all(),
        others=Stall.query.filter(Stall.status.in_(["need_more", "awaiting_payment", "active", "rejected"]))
        .order_by(Stall.id.desc()).all(),
        batches=Batch.query.filter_by(verified=False).all())


@bp.route("/gian-hang/<int:sid>")
@roles_required("bql")
def review(sid):
    return render_template("bql/review.html", s=db.get_or_404(Stall, sid))


@bp.route("/gian-hang/<int:sid>/xu-ly", methods=["POST"])
@roles_required("bql")
def decide(sid):
    s = db.get_or_404(Stall, sid)
    act = request.form.get("action")
    note = request.form.get("note", "").strip()
    link = url_for("merchant.dashboard")
    if act == "pass" and s.status == "submitted":
        # Hồ sơ đạt → hệ thống xác thực & phát sinh phí gian hàng
        s.verified = True
        s.fee = calc_stall_fee(s.category, s.months)
        s.status = "awaiting_payment"
        notify(s.owner_id, f"Hồ sơ “{s.name}” đạt yêu cầu. Vui lòng thanh toán phí gian hàng.", link)
    elif act == "need_more" and s.status == "submitted":
        if not note:
            flash("Hãy ghi rõ nội dung cần bổ sung.", "danger")
            return redirect(url_for("bql.review", sid=sid))
        s.status, s.bql_note = "need_more", note
        notify(s.owner_id, f"Hồ sơ “{s.name}” cần bổ sung: {note}", url_for("merchant.stall_form"))
    elif act == "approve" and s.status == "paid":
        s.status, s.approved_at = "active", datetime.now()
        notify(s.owner_id, f"Gian hàng số “{s.name}” đã được kích hoạt. Bạn có thể đăng bán ngay!", link)
    elif act == "reject" and s.status in ("submitted", "paid"):
        s.status, s.bql_note = "rejected", note or "Không đáp ứng điều kiện"
        notify(s.owner_id, f"Hồ sơ “{s.name}” bị từ chối: {s.bql_note}", link)
    else:
        flash("Thao tác không hợp lệ ở trạng thái hiện tại.", "warning")
        return redirect(url_for("bql.dashboard"))
    db.session.commit()
    flash("Đã xử lý hồ sơ.", "success")
    return redirect(url_for("bql.dashboard"))


@bp.route("/lo-hang/<int:bid>/xac-minh", methods=["POST"])
@roles_required("bql")
def verify_batch(bid):
    b = db.get_or_404(Batch, bid)
    b.verified = True
    notify(b.stall.owner_id, f"Lô hàng {b.batch_code} đã được xác minh", url_for("merchant.traceability"))
    db.session.commit()
    flash("Đã xác minh lô hàng.", "success")
    return redirect(url_for("bql.dashboard"))
