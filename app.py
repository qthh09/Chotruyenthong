"""Chợ địa phương số – ứng dụng Flask.

Chạy:  python app.py   →  http://127.0.0.1:5000
"""
import os

from flask import Flask, g, render_template

from config import Config
from helpers import (DELIVERY_LABEL, PAYMENT_LABEL, ROLE_LABEL, badge, dt, load_user, money)
from models import Notification, db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.init_app(app)

    from routes.admin import bp as admin_bp
    from routes.auth import bp as auth_bp
    from routes.bql import bp as bql_bp
    from routes.merchant import bp as merchant_bp
    from routes.ops import bp as ops_bp
    from routes.shop import bp as shop_bp
    for bp in (shop_bp, auth_bp, merchant_bp, bql_bp, ops_bp, admin_bp):
        app.register_blueprint(bp)

    app.before_request(load_user)
    app.add_template_filter(money, "money")
    app.add_template_filter(dt, "dt")
    app.add_template_filter(badge, "badge")
    app.jinja_env.globals["zip"] = zip

    @app.context_processor
    def inject():
        unread = 0
        if g.get("user"):
            unread = Notification.query.filter_by(user_id=g.user.id, is_read=False).count()
        from flask import session
        cart_count = sum(session.get("cart", {}).values())
        return dict(unread=unread, cart_count=cart_count, ROLE_LABEL=ROLE_LABEL,
                    DELIVERY_LABEL=DELIVERY_LABEL, PAYMENT_LABEL=PAYMENT_LABEL,
                    DISTRICTS=app.config["DISTRICTS"], TIME_WINDOWS=app.config["TIME_WINDOWS"],
                    cfg=app.config)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, msg="Không tìm thấy trang bạn cần."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code=413, msg="Tệp tải lên quá lớn (tối đa 8 MB)."), 413

    with app.app_context():
        db.create_all()
        from seed import seed_data
        seed_data()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
