from functools import wraps

from flask import flash, g, redirect, request, session, url_for
from markupsafe import Markup

from models import Notification, User, db

ROLE_HOME = {
    "customer": "shop.index",
    "merchant": "merchant.dashboard",
    "shipper": "ops.shipper",
    "operator": "ops.dispatch",
    "bql": "bql.dashboard",
    "admin": "admin.dashboard",
}
ROLE_LABEL = {
    "customer": "Khách hàng", "merchant": "Người bán", "shipper": "Shipper địa phương",
    "operator": "Đơn vị vận hành", "bql": "Ban quản lý chợ", "admin": "Quản trị hệ thống",
}

LABELS = {
    "stall": {
        "draft": ("Nháp", "secondary"), "submitted": ("Chờ BQL kiểm tra", "warning"),
        "need_more": ("Cần bổ sung hồ sơ", "danger"), "awaiting_payment": ("Chờ thanh toán phí", "info"),
        "paid": ("Chờ phê duyệt", "primary"), "active": ("Đang hoạt động", "success"),
        "rejected": ("Bị từ chối", "dark"),
    },
    "sub": {
        "pending_payment": ("Chờ thanh toán", "secondary"), "new": ("Đơn mới", "warning"),
        "accepted": ("Đã xác nhận", "info"), "preparing": ("Đang chuẩn bị", "info"),
        "ready": ("Sẵn sàng giao", "primary"), "ship_requested": ("Đã đặt ship", "primary"),
        "handed_over": ("Đã bàn giao shipper", "primary"), "delivering": ("Đang giao", "primary"),
        "completed": ("Hoàn tất", "success"), "rejected": ("Từ chối / hết hàng", "danger"),
        "cancelled": ("Đã huỷ", "dark"),
    },
    "order": {
        "awaiting_payment": ("Chờ thanh toán", "secondary"), "processing": ("Đang xử lý", "primary"),
        "completed": ("Hoàn tất", "success"), "cancelled": ("Đã huỷ", "dark"),
    },
    "deliv": {
        "pending": ("Chờ tìm shipper", "warning"), "waiting_batch": ("Chờ gom đơn", "warning"),
        "assigned": ("Đã có shipper", "info"), "picked": ("Đã lấy hàng", "primary"),
        "delivering": ("Đang giao", "primary"), "delivered": ("Đã giao", "success"),
    },
    "pay": {"pending": ("Chưa thanh toán", "warning"), "paid": ("Đã thanh toán", "success"),
            "failed": ("Thất bại", "danger")},
}
DELIVERY_LABEL = {"pickup": "Tự đến lấy", "instant": "Giao ngay", "economy": "Giao tiết kiệm"}
PAYMENT_LABEL = {"cod": "Thanh toán khi nhận hàng (COD)", "bank": "Chuyển khoản / QR ngân hàng",
                 "wallet": "Ví điện tử"}


def badge(status, kind):
    label, color = LABELS.get(kind, {}).get(status, (status, "secondary"))
    return Markup(f'<span class="badge text-bg-{color}">{label}</span>')


def money(v):
    return "{:,.0f}".format(v or 0).replace(",", ".") + "đ"


def dt(v, fmt="%d/%m/%Y %H:%M"):
    return v.strftime(fmt) if v else ""


def load_user():
    uid = session.get("uid")
    g.user = db.session.get(User, uid) if uid else None
    if g.user and g.user.is_locked:
        session.clear()
        g.user = None


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not g.user:
            flash("Vui lòng đăng nhập để tiếp tục.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return f(*a, **kw)
    return wrapper


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        @login_required
        def wrapper(*a, **kw):
            if g.user.role not in roles and g.user.role != "admin":
                flash("Bạn không có quyền truy cập trang này.", "danger")
                return redirect(url_for(ROLE_HOME.get(g.user.role, "shop.index")))
            return f(*a, **kw)
        return wrapper
    return deco


def notify(user_id, message, link=None):
    if user_id:
        db.session.add(Notification(user_id=user_id, message=message, link=link))


def notify_role(role, message, link=None):
    for u in User.query.filter_by(role=role).all():
        notify(u.id, message, link)


def get_cart():
    return session.setdefault("cart", {})


def calc_stall_fee(category, months):
    base = (category.fee_per_month if category else 200000) * months
    discount = {3: 0, 6: 0.05, 12: 0.10}.get(months, 0)
    return int(base * (1 - discount))


def refresh_order_status(order):
    subs = order.suborders
    active = [s for s in subs if s.status not in ("rejected", "cancelled")]
    if not active:
        order.status = "cancelled"
    elif all(s.status == "completed" for s in active):
        order.status = "completed"
        if order.payment_method == "cod":
            order.payment_status = "paid"
    elif all(s.status == "pending_payment" for s in active):
        order.status = "awaiting_payment"
    else:
        order.status = "processing"


# ------------------------------------------------------------ thống kê
def revenue_series(stall_id=None, days=14, months=6):
    """Doanh thu (chỉ tính đơn Hoàn tất) theo ngày và theo tháng."""
    from datetime import date, timedelta
    from models import SubOrder
    q = SubOrder.query.filter(SubOrder.status == "completed")
    if stall_id:
        q = q.filter(SubOrder.stall_id == stall_id)
    subs = q.all()
    today = date.today()
    by_day = {today - timedelta(days=i): 0 for i in range(days - 1, -1, -1)}
    by_month = {}
    y, m = today.year, today.month
    for _ in range(months):
        by_month[(y, m)] = 0
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    for s in subs:
        d = (s.completed_at or s.created_at)
        if d.date() in by_day:
            by_day[d.date()] += s.subtotal
        if (d.year, d.month) in by_month:
            by_month[(d.year, d.month)] += s.subtotal
    return {
        "day_labels": [d.strftime("%d/%m") for d in by_day],
        "day_values": list(by_day.values()),
        "month_labels": [f"{m:02d}/{y}" for (y, m) in reversed(list(by_month))],
        "month_values": list(reversed(list(by_month.values()))),
        "today": by_day[today],
        "this_month": by_month[(today.year, today.month)],
        "total": sum(s.subtotal for s in subs),
    }
