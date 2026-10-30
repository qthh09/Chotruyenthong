import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "doi-khoa-bi-mat-nay-khi-trien-khai")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "cho_so.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

    # Phí giao hàng (mỗi đơn của một gian hàng)
    SHIP_FEE_INSTANT = 25000
    SHIP_FEE_ECONOMY = 10000
    # Tiêu chí gom đơn
    MAX_LOAD_KG = 20
    MAX_STOPS = 6

    DISTRICTS = [
        "Ba Đình", "Hoàn Kiếm", "Đống Đa", "Hai Bà Trưng", "Cầu Giấy", "Thanh Xuân",
        "Tây Hồ", "Long Biên", "Hà Đông", "Nam Từ Liêm", "Bắc Từ Liêm",
    ]
    TIME_WINDOWS = ["Sáng 8h-11h", "Chiều 13h-17h", "Tối 17h-20h"]
