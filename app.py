# -*- coding: utf-8 -*-
"""
app.py
------
Web bán hàng thật cho VEQISTU — phong cách giống trang shop Shopee
(https://shopee.vn/veqistu), có giỏ hàng, đặt hàng (chuyển khoản QR VietQR
hoặc COD), và trang quản trị để thêm/sửa sản phẩm + xem đơn hàng.

Chạy thử ở máy bạn:
    pip install --break-system-packages -r requirements.txt
    python3 app.py
    # mở http://127.0.0.1:5000
"""

import json
import os
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask, redirect, render_template, request, session, url_for, flash, jsonify
)

import db
from seed_data import CATEGORIES, PRODUCTS, COMMON_SPECS, DEFAULT_COLORS, DEFAULT_SIZES, build_description

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "doi-chuoi-nay-truoc-khi-deploy-that")
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # tối đa 60MB mỗi lần lưu (ảnh + video đánh giá)

# ---------- Cấu hình upload ảnh sản phẩm ----------
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_VIDEO_EXT = {"mp4", "webm", "mov", "mkv"}


def _allowed_image(filename):
    return bool(filename) and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


def _allowed_video(filename):
    return bool(filename) and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXT


def _save_uploaded_file(file_storage):
    """Lưu 1 file ảnh upload, trả về đường dẫn tương đối trong static/ (vd 'uploads/xxxx.jpg') hoặc None."""
    if not file_storage or not file_storage.filename or not _allowed_image(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, fname))
    return f"uploads/{fname}"


def _save_uploaded_video(file_storage):
    """Lưu 1 file video upload (đánh giá sản phẩm), trả về đường dẫn tương đối trong static/ hoặc None."""
    if not file_storage or not file_storage.filename or not _allowed_video(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, fname))
    return f"uploads/{fname}"

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "veqistu_admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Veqistu@2026")

# Thông tin ngân hàng để tạo QR chuyển khoản (VietQR) — điền qua biến môi trường
BANK_BIN = os.environ.get("BANK_BIN", "")          # vd: 970436 (Vietcombank)
BANK_ACCOUNT_NO = os.environ.get("BANK_ACCOUNT_NO", "")
BANK_ACCOUNT_NAME = os.environ.get("BANK_ACCOUNT_NAME", "")

SHOP_NAME = os.environ.get("SHOP_NAME", "VEQISTU")


# ---------- Khởi tạo DB + seed dữ liệu thật lần đầu ----------
def ensure_seeded():
    db.init_db()
    existing = db.query("SELECT COUNT(*) AS c FROM product", one=True)
    if existing["c"] > 0:
        return
    cat_ids = {}
    for name in CATEGORIES:
        cid = db.execute("INSERT OR IGNORE INTO category (name) VALUES (?)", (name,))
        row = db.query("SELECT id FROM category WHERE name=?", (name,), one=True)
        cat_ids[name] = row["id"]

    for (name, price, original_price, cat_name, rating, sold, color_hex) in PRODUCTS:
        db.execute(
            """INSERT INTO product
               (name, category_id, price, original_price, rating, sold_count, stock,
                description, material, style, origin, collar, colors, sizes, color_hex)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                name, cat_ids[cat_name], price, original_price, rating, sold, 100,
                build_description(name), COMMON_SPECS["material"], COMMON_SPECS["style"],
                COMMON_SPECS["origin"], COMMON_SPECS["collar"], DEFAULT_COLORS, DEFAULT_SIZES,
                color_hex,
            ),
        )


with app.app_context():
    ensure_seeded()


# ---------- Helpers ----------
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def get_variants(product_id):
    return db.query(
        "SELECT * FROM product_variant WHERE product_id=? ORDER BY color, size", (product_id,)
    )


def find_variant(product_id, color, size):
    return db.query(
        "SELECT * FROM product_variant WHERE product_id=? AND color=? AND size=?",
        (product_id, color, size), one=True,
    )


def get_reviews(product_id):
    return db.query("SELECT * FROM review WHERE product_id=? ORDER BY id DESC", (product_id,))


def review_stats(reviews):
    count = len(reviews)
    avg = round(sum(r["rating"] for r in reviews) / count, 1) if count else 0
    return count, avg


def get_shop_blocks(active_only=True):
    sql = "SELECT * FROM shop_page_block"
    if active_only:
        sql += " WHERE active=1"
    sql += " ORDER BY display_order ASC, id ASC"
    return db.query(sql)


def get_description_blocks(product_id):
    return db.query(
        "SELECT * FROM product_description_block WHERE product_id=? ORDER BY display_order ASC, id ASC",
        (product_id,),
    )


def get_color_images(product_id):
    return db.query("SELECT * FROM product_color_image WHERE product_id=?", (product_id,))


# ---------- Voucher (mã giảm giá) ----------
def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def get_active_vouchers():
    """Voucher đang bật, còn trong thời hạn, chưa hết lượt dùng."""
    now = datetime.now()
    result = []
    for v in db.query("SELECT * FROM voucher WHERE active=1"):
        start, end = _parse_dt(v["start_at"]), _parse_dt(v["end_at"])
        if start and now < start:
            continue
        if end and now > end:
            continue
        if v["total_usage_limit"] is not None and v["used_count"] >= v["total_usage_limit"]:
            continue
        result.append(v)
    return result


def get_voucher_product_ids(voucher_id):
    return {row["product_id"] for row in db.query("SELECT product_id FROM voucher_product WHERE voucher_id=?", (voucher_id,))}


def voucher_applies_to_product(voucher, product_id):
    return voucher["scope"] == "shop" or product_id in get_voucher_product_ids(voucher["id"])


def get_vouchers_for_product(product_id):
    return [v for v in get_active_vouchers() if voucher_applies_to_product(v, product_id)]


def get_voucher_eligible_subtotal(voucher, cart):
    if voucher["scope"] == "shop":
        return sum(i["price"] * i["qty"] for i in cart)
    product_ids = get_voucher_product_ids(voucher["id"])
    return sum(i["price"] * i["qty"] for i in cart if i["product_id"] in product_ids)


def compute_voucher_discount(voucher, eligible_subtotal):
    if eligible_subtotal < (voucher["min_order_value"] or 0):
        return 0
    if voucher["discount_type"] == "percent":
        raw = eligible_subtotal * voucher["discount_value"] / 100
        if voucher["max_discount_amount"]:
            raw = min(raw, voucher["max_discount_amount"])
        return int(raw)
    return min(voucher["discount_value"], eligible_subtotal)


def get_voucher_by_code(code):
    return db.query("SELECT * FROM voucher WHERE code=?", (code.strip().upper(),), one=True)


def get_applied_voucher_and_discount(cart):
    """Voucher khách đã nhập/áp dụng (lưu trong session) — trả về (voucher, số tiền giảm) hoặc (None, 0)."""
    code = session.get("voucher_code")
    if not code or not cart:
        return None, 0
    voucher = get_voucher_by_code(code)
    if not voucher or not voucher["active"]:
        return None, 0
    now = datetime.now()
    start, end = _parse_dt(voucher["start_at"]), _parse_dt(voucher["end_at"])
    if start and now < start:
        return None, 0
    if end and now > end:
        return None, 0
    if voucher["total_usage_limit"] is not None and voucher["used_count"] >= voucher["total_usage_limit"]:
        return None, 0
    subtotal = get_voucher_eligible_subtotal(voucher, cart)
    if subtotal < (voucher["min_order_value"] or 0):
        return None, 0
    return voucher, compute_voucher_discount(voucher, subtotal)


# ---------- Combo Khuyến Mãi ----------
def get_active_combos():
    return db.query("SELECT * FROM combo_deal WHERE active=1")


def get_combo_product_ids(combo_id):
    return {row["product_id"] for row in db.query("SELECT product_id FROM combo_deal_product WHERE combo_id=?", (combo_id,))}


def combo_applies_to_product(combo, product_id):
    return combo["scope"] == "shop" or product_id in get_combo_product_ids(combo["id"])


def get_combos_for_product(product_id):
    return [c for c in get_active_combos() if combo_applies_to_product(c, product_id)]


def compute_combo_discount(cart):
    total_discount = 0
    applied = []
    for combo in get_active_combos():
        if combo["scope"] == "shop":
            qty = sum(i["qty"] for i in cart)
        else:
            pids = get_combo_product_ids(combo["id"])
            qty = sum(i["qty"] for i in cart if i["product_id"] in pids)
        if qty >= combo["min_quantity"]:
            total_discount += combo["discount_amount"]
            applied.append(combo)
    return total_discount, applied


# ---------- Flash Sale (FLS) ----------
def get_active_flash_sale():
    now = datetime.now()
    for s in db.query("SELECT * FROM flash_sale WHERE active=1"):
        start, end = _parse_dt(s["start_at"]), _parse_dt(s["end_at"])
        if start and end and start <= now <= end:
            return s
    return None


def get_flash_sale_items(flash_sale_id):
    return db.query(
        """SELECT fsi.*, p.name AS product_name, p.image_path, p.color_hex, p.price AS normal_price
           FROM flash_sale_item fsi JOIN product p ON p.id = fsi.product_id
           WHERE fsi.flash_sale_id=?""",
        (flash_sale_id,),
    )


def get_flash_sale_item_for_product(product_id):
    sale = get_active_flash_sale()
    if not sale:
        return None, None
    item = db.query(
        "SELECT * FROM flash_sale_item WHERE flash_sale_id=? AND product_id=?",
        (sale["id"], product_id), one=True,
    )
    return sale, item


def get_cart():
    return session.setdefault("cart", [])  # list of {product_id, name, price, variant, qty, is_flash_sale}


def cart_total(cart):
    return sum(item["price"] * item["qty"] for item in cart)


def vietqr_url(amount, message):
    if not (BANK_BIN and BANK_ACCOUNT_NO):
        return None
    from urllib.parse import quote
    base = f"https://img.vietqr.io/image/{BANK_BIN}-{BANK_ACCOUNT_NO}-compact2.png"
    return f"{base}?amount={int(amount)}&addInfo={quote(message)}&accountName={quote(BANK_ACCOUNT_NAME)}"


@app.context_processor
def inject_globals():
    return {"shop_name": SHOP_NAME, "cart_count": sum(i["qty"] for i in get_cart())}


# ---------- Trang khách hàng ----------
@app.route("/")
def index():
    category_id = request.args.get("category", type=int)
    sort = request.args.get("sort", "pho_bien")

    sql = """SELECT p.*,
                (SELECT COUNT(DISTINCT price) FROM product_variant WHERE product_id=p.id) AS variant_price_count
             FROM product p WHERE active=1"""
    params = []
    if category_id:
        sql += " AND category_id=?"
        params.append(category_id)

    if sort == "moi_nhat":
        sql += " ORDER BY created_at DESC"
    elif sort == "ban_chay":
        sql += " ORDER BY sold_count DESC"
    elif sort == "gia_tang":
        sql += " ORDER BY price ASC"
    elif sort == "gia_giam":
        sql += " ORDER BY price DESC"
    else:
        sql += " ORDER BY rating DESC, sold_count DESC"

    products = db.query(sql, params)
    categories = db.query("SELECT * FROM category ORDER BY id")
    return render_template(
        "index.html", products=products, categories=categories,
        active_category=category_id, active_sort=sort,
    )


@app.route("/san-pham/<int:product_id>")
def product_detail(product_id):
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404
    related = db.query(
        "SELECT * FROM product WHERE category_id=? AND id<>? AND active=1 LIMIT 6",
        (product["category_id"], product_id),
    )
    variants = get_variants(product_id)
    variants_json = json.dumps([dict(v) for v in variants])
    reviews = get_reviews(product_id)
    review_count, review_avg = review_stats(reviews)
    description_blocks = get_description_blocks(product_id)
    color_images = get_color_images(product_id)
    color_images_map = {row["color"]: url_for("static", filename=row["image_path"]) for row in color_images}
    color_images_json = json.dumps(color_images_map)

    vouchers = get_vouchers_for_product(product_id)
    combos = get_combos_for_product(product_id)
    flash_sale, flash_sale_item = get_flash_sale_item_for_product(product_id)
    flash_sale_remaining = None
    display_price = product["price"]
    if flash_sale_item:
        flash_sale_remaining = max(flash_sale_item["stock_limit"] - flash_sale_item["sold_in_sale"], 0)
        if flash_sale_remaining > 0:
            display_price = flash_sale_item["sale_price"]
        else:
            flash_sale_item = None

    best_voucher = None
    best_voucher_discount = 0
    for v in vouchers:
        if display_price < (v["min_order_value"] or 0):
            continue
        d = compute_voucher_discount(v, display_price)
        if d > best_voucher_discount:
            best_voucher_discount = d
            best_voucher = v
    price_after_voucher = (display_price - best_voucher_discount) if best_voucher else None

    shop_stats = {
        "total_products": db.query("SELECT COUNT(*) AS c FROM product WHERE active=1", one=True)["c"],
        "rating": round((db.query("SELECT AVG(rating) AS a FROM product WHERE active=1", one=True)["a"] or 5.0), 1),
    }
    top_products = db.query("SELECT * FROM product WHERE active=1 ORDER BY sold_count DESC LIMIT 5")

    return render_template("product_detail.html", p=product, related=related,
                            variants=variants, variants_json=variants_json,
                            reviews=reviews, review_count=review_count, review_avg=review_avg,
                            description_blocks=description_blocks, color_images_json=color_images_json,
                            vouchers=vouchers, combos=combos,
                            flash_sale=flash_sale, flash_sale_item=flash_sale_item,
                            flash_sale_remaining=flash_sale_remaining, display_price=display_price,
                            best_voucher=best_voucher, best_voucher_discount=best_voucher_discount,
                            price_after_voucher=price_after_voucher,
                            shop_stats=shop_stats, top_products=top_products)


@app.route("/cart/add", methods=["POST"])
def cart_add():
    product_id = int(request.form["product_id"])
    qty = max(1, int(request.form.get("qty", 1)))
    color = request.form.get("color", "")
    size = request.form.get("size", "")
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404

    # Nếu sản phẩm có bảng phân loại (màu/size riêng giá + tồn kho) thì dùng đúng
    # giá/tồn kho của phân loại đó; không thì dùng giá/tồn kho chung của sản phẩm
    # (tương thích ngược với sản phẩm cũ chưa khai báo phân loại chi tiết).
    variant_row = find_variant(product_id, color, size) if (color or size) else None
    unit_price = variant_row["price"] if variant_row else product["price"]
    available_stock = variant_row["stock"] if variant_row else product["stock"]

    # Giá theo Flash Sale (nếu sản phẩm đang trong 1 đợt FLS và còn suất)
    is_flash_sale = False
    flash_sale_item_id = None
    _, sale_item = get_flash_sale_item_for_product(product_id)
    if sale_item:
        remaining = max(sale_item["stock_limit"] - sale_item["sold_in_sale"], 0)
        if remaining > 0:
            unit_price = sale_item["sale_price"]
            available_stock = min(available_stock, remaining)
            is_flash_sale = True
            flash_sale_item_id = sale_item["id"]

    cart = get_cart()
    variant = f"{color} / {size}".strip(" /")
    for item in cart:
        if item["product_id"] == product_id and item["variant"] == variant and item.get("is_flash_sale") == is_flash_sale:
            item["qty"] = min(item["qty"] + qty, max(available_stock, 1))
            break
    else:
        cart.append({
            "product_id": product_id, "name": product["name"], "price": unit_price,
            "variant": variant, "qty": min(qty, max(available_stock, 1)), "color_hex": product["color_hex"],
            "is_flash_sale": is_flash_sale, "flash_sale_item_id": flash_sale_item_id,
        })
    session.modified = True

    if request.form.get("buy_now"):
        return redirect(url_for("checkout"))
    return redirect(url_for("cart_view"))


@app.route("/cart")
def cart_view():
    cart = get_cart()
    subtotal = cart_total(cart)
    voucher, voucher_discount = get_applied_voucher_and_discount(cart)
    combo_discount, applied_combos = compute_combo_discount(cart)
    grand_total = max(subtotal - voucher_discount - combo_discount, 0)
    return render_template(
        "cart.html", cart=cart, total=subtotal,
        voucher=voucher, voucher_discount=voucher_discount,
        applied_combos=applied_combos, combo_discount=combo_discount,
        grand_total=grand_total,
    )


@app.route("/cart/voucher/ap-dung", methods=["POST"])
def cart_apply_voucher():
    code = request.form.get("voucher_code", "").strip().upper()
    cart = get_cart()
    if not code:
        flash("Vui lòng nhập mã voucher.")
        return redirect(url_for("cart_view"))
    if not cart:
        flash("Giỏ hàng đang trống.")
        return redirect(url_for("cart_view"))
    voucher = get_voucher_by_code(code)
    if not voucher or not voucher["active"]:
        flash("Mã voucher không tồn tại hoặc đã ngừng áp dụng.")
        return redirect(url_for("cart_view"))
    now = datetime.now()
    start, end = _parse_dt(voucher["start_at"]), _parse_dt(voucher["end_at"])
    if start and now < start:
        flash("Mã voucher chưa đến thời gian sử dụng.")
        return redirect(url_for("cart_view"))
    if end and now > end:
        flash("Mã voucher đã hết hạn sử dụng.")
        return redirect(url_for("cart_view"))
    if voucher["total_usage_limit"] is not None and voucher["used_count"] >= voucher["total_usage_limit"]:
        flash("Mã voucher đã hết lượt sử dụng.")
        return redirect(url_for("cart_view"))
    eligible_subtotal = get_voucher_eligible_subtotal(voucher, cart)
    if eligible_subtotal < (voucher["min_order_value"] or 0):
        min_val = "{:,.0f}".format(voucher["min_order_value"] or 0)
        flash(f"Đơn hàng (áp dụng cho sản phẩm hợp lệ) cần tối thiểu {min_val}đ để dùng mã này.")
        return redirect(url_for("cart_view"))
    session["voucher_code"] = voucher["code"]
    session.modified = True
    flash(f"Đã áp dụng mã giảm giá {voucher['code']}.")
    return redirect(url_for("cart_view"))


@app.route("/cart/voucher/huy")
def cart_remove_voucher():
    session.pop("voucher_code", None)
    session.modified = True
    return redirect(url_for("cart_view"))


@app.route("/cart/remove/<int:index>")
def cart_remove(index):
    cart = get_cart()
    if 0 <= index < len(cart):
        cart.pop(index)
        session.modified = True
    return redirect(url_for("cart_view"))


@app.route("/cart/update/<int:index>", methods=["POST"])
def cart_update(index):
    cart = get_cart()
    qty = max(1, int(request.form.get("qty", 1)))
    if 0 <= index < len(cart):
        cart[index]["qty"] = qty
        session.modified = True
    return redirect(url_for("cart_view"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = get_cart()
    if not cart:
        return redirect(url_for("index"))

    subtotal = cart_total(cart)
    voucher, voucher_discount = get_applied_voucher_and_discount(cart)
    combo_discount, applied_combos = compute_combo_discount(cart)
    discount_amount = voucher_discount + combo_discount
    grand_total = max(subtotal - discount_amount, 0)

    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        address = request.form["address"].strip()
        payment_method = request.form["payment_method"]
        note = request.form.get("note", "").strip()

        if not (name and phone and address):
            flash("Vui lòng điền đầy đủ Họ tên, Số điện thoại và Địa chỉ.")
            return render_template("checkout.html", cart=cart, total=subtotal, voucher=voucher,
                                    voucher_discount=voucher_discount, applied_combos=applied_combos,
                                    combo_discount=combo_discount, grand_total=grand_total)

        order_id = db.execute(
            """INSERT INTO orders (customer_name, phone, address, payment_method, total_amount, note,
               voucher_code, discount_amount)
               VALUES (?,?,?,?,?,?,?,?)""",
            (name, phone, address, payment_method, grand_total, note,
             voucher["code"] if voucher else None, discount_amount),
        )
        for item in cart:
            db.execute(
                """INSERT INTO order_item (order_id, product_id, product_name, variant, unit_price, quantity)
                   VALUES (?,?,?,?,?,?)""",
                (order_id, item["product_id"], item["name"], item["variant"], item["price"], item["qty"]),
            )
            if item.get("is_flash_sale") and item.get("flash_sale_item_id"):
                db.execute(
                    "UPDATE flash_sale_item SET sold_in_sale = sold_in_sale + ? WHERE id=?",
                    (item["qty"], item["flash_sale_item_id"]),
                )
        if voucher:
            db.execute("UPDATE voucher SET used_count = used_count + 1 WHERE id=?", (voucher["id"],))
        session["cart"] = []
        session.pop("voucher_code", None)
        session.modified = True
        return redirect(url_for("order_success", order_id=order_id))

    return render_template("checkout.html", cart=cart, total=subtotal, voucher=voucher,
                            voucher_discount=voucher_discount, applied_combos=applied_combos,
                            combo_discount=combo_discount, grand_total=grand_total)


@app.route("/don-hang/<int:order_id>/thanh-cong")
def order_success(order_id):
    order = db.query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    items = db.query("SELECT * FROM order_item WHERE order_id=?", (order_id,))
    qr = None
    if order["payment_method"] == "bank_transfer":
        qr = vietqr_url(order["total_amount"], f"DH{order_id} {order['customer_name']}")
    return render_template("order_success.html", order=order, items=items, qr=qr,
                            bank_configured=bool(BANK_BIN and BANK_ACCOUNT_NO))


# ---------- Trang quản trị ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Sai tài khoản hoặc mật khẩu."
    return render_template("admin/login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    products = db.query("SELECT p.*, c.name AS category_name FROM product p LEFT JOIN category c ON p.category_id=c.id ORDER BY p.id DESC")
    return render_template("admin/dashboard.html", products=products)


@app.route("/admin/san-pham/moi", methods=["GET", "POST"])
@admin_required
def admin_product_new():
    categories = db.query("SELECT * FROM category ORDER BY id")
    if request.method == "POST":
        new_id = _save_product(None, request.form, request.files, categories)
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/product_form.html", p=None, categories=categories, variants_json="[]")


@app.route("/admin/san-pham/<int:product_id>/sua", methods=["GET", "POST"])
@admin_required
def admin_product_edit(product_id):
    categories = db.query("SELECT * FROM category ORDER BY id")
    p = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if request.method == "POST":
        _save_product(product_id, request.form, request.files, categories)
        return redirect(url_for("admin_dashboard"))
    variants = get_variants(product_id)
    variants_json = json.dumps([dict(v) for v in variants])
    return render_template("admin/product_form.html", p=p, categories=categories, variants_json=variants_json)


def _save_product(product_id, form, files, categories):
    category_id = int(form["category_id"])

    # Ảnh chính: nếu có upload ảnh mới thì dùng ảnh mới, không thì giữ ảnh cũ (khi sửa)
    new_image = _save_uploaded_file(files.get("image"))
    if new_image:
        image_path = new_image
    elif product_id:
        existing = db.query("SELECT image_path FROM product WHERE id=?", (product_id,), one=True)
        image_path = existing["image_path"] if existing else None
    else:
        image_path = None

    # Ảnh thêm cho phần mô tả: nếu có chọn ảnh mới thì THAY TOÀN BỘ ảnh cũ, không thì giữ nguyên
    new_gallery_files = [f for f in files.getlist("gallery_images") if f and f.filename]
    if new_gallery_files:
        saved = [p for p in (_save_uploaded_file(f) for f in new_gallery_files) if p]
        gallery_images = ",".join(saved)
    elif product_id:
        existing = db.query("SELECT gallery_images FROM product WHERE id=?", (product_id,), one=True)
        gallery_images = existing["gallery_images"] if existing else ""
    else:
        gallery_images = ""

    # Video sản phẩm: nếu có upload video mới thì thay video cũ, không thì giữ nguyên
    new_video = _save_uploaded_video(files.get("video"))
    if new_video:
        video_path = new_video
    elif product_id:
        existing = db.query("SELECT video_path FROM product WHERE id=?", (product_id,), one=True)
        video_path = existing["video_path"] if existing else None
    else:
        video_path = None

    # ----- Bảng phân loại hàng (Màu sắc x Size) -----
    try:
        raw_variants = json.loads(form.get("variants_json", "[]") or "[]")
    except (ValueError, TypeError):
        raw_variants = []
    parsed_variants = []
    for v in raw_variants:
        color = str(v.get("color", "")).strip()
        size = str(v.get("size", "")).strip()
        price_val = v.get("price")
        if not color or not size or price_val in (None, ""):
            continue
        try:
            v_price = int(price_val)
            v_stock = int(v.get("stock") or 0)
        except (ValueError, TypeError):
            continue
        parsed_variants.append({
            "color": color, "size": size, "price": v_price, "stock": v_stock,
            "sku": str(v.get("sku", "")).strip(), "gtin": str(v.get("gtin", "")).strip(),
        })

    # Nếu có bảng phân loại thì giá/tồn kho hiển thị của sản phẩm = giá thấp nhất / tổng tồn kho
    if parsed_variants:
        base_price = min(v["price"] for v in parsed_variants)
        base_stock = sum(v["stock"] for v in parsed_variants)
    else:
        base_price = int(form["price"])
        base_stock = int(form.get("stock", 100))

    fields = (
        form["name"].strip(), category_id, base_price,
        int(form["original_price"]) if form.get("original_price") else None,
        form.get("material", ""), form.get("style", ""), form.get("origin", "Việt Nam"),
        form.get("collar", ""), form.get("colors", DEFAULT_COLORS), form.get("sizes", DEFAULT_SIZES),
        base_stock, form.get("description", ""), form.get("color_hex", "#ee4d2d"),
        image_path, gallery_images, video_path, 1 if form.get("active") else 0,
        form.get("brand", "No brand"), form.get("pattern", ""), form.get("season", ""),
        form.get("sleeve_length", ""), form.get("garment_length", ""), form.get("fit", ""),
        int(form.get("weight_grams") or 100),
        int(form.get("package_length_cm") or 1), int(form.get("package_width_cm") or 1),
        int(form.get("package_height_cm") or 1),
        1 if form.get("ship_hoa_toc_enabled") else 0, int(form.get("ship_hoa_toc_fee") or 22000),
        1 if form.get("ship_nhanh_enabled") else 0, int(form.get("ship_nhanh_fee") or 16500),
        1 if form.get("is_preorder") else 0,
    )
    if product_id:
        db.execute(
            """UPDATE product SET name=?, category_id=?, price=?, original_price=?, material=?,
               style=?, origin=?, collar=?, colors=?, sizes=?, stock=?, description=?, color_hex=?,
               image_path=?, gallery_images=?, video_path=?, active=?,
               brand=?, pattern=?, season=?, sleeve_length=?, garment_length=?, fit=?,
               weight_grams=?, package_length_cm=?, package_width_cm=?, package_height_cm=?,
               ship_hoa_toc_enabled=?, ship_hoa_toc_fee=?, ship_nhanh_enabled=?, ship_nhanh_fee=?,
               is_preorder=?
               WHERE id=?""",
            fields + (product_id,),
        )
        new_product_id = product_id
    else:
        new_product_id = db.execute(
            """INSERT INTO product (name, category_id, price, original_price, material, style, origin,
               collar, colors, sizes, stock, description, color_hex, image_path, gallery_images, video_path, active,
               brand, pattern, season, sleeve_length, garment_length, fit,
               weight_grams, package_length_cm, package_width_cm, package_height_cm,
               ship_hoa_toc_enabled, ship_hoa_toc_fee, ship_nhanh_enabled, ship_nhanh_fee, is_preorder,
               rating, sold_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,5.0,0)""",
            fields,
        )

    # Ghi lại toàn bộ bảng phân loại (xoá cũ, thêm lại theo dữ liệu mới nhất)
    db.execute("DELETE FROM product_variant WHERE product_id=?", (new_product_id,))
    for v in parsed_variants:
        db.execute(
            """INSERT INTO product_variant (product_id, color, size, price, stock, sku, gtin)
               VALUES (?,?,?,?,?,?,?)""",
            (new_product_id, v["color"], v["size"], v["price"], v["stock"], v["sku"], v["gtin"]),
        )
    return new_product_id


@app.route("/admin/san-pham/<int:product_id>/xoa")
@admin_required
def admin_product_delete(product_id):
    """Ẩn/bỏ ẩn sản phẩm (không xoá dữ liệu) — bấm lại để đảo trạng thái."""
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if product:
        db.execute("UPDATE product SET active=? WHERE id=?", (0 if product["active"] else 1, product_id))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/san-pham/<int:product_id>/xoa-han")
@admin_required
def admin_product_delete_permanent(product_id):
    """Xoá vĩnh viễn sản phẩm khỏi hệ thống (khác với Ẩn — không thể khôi phục)."""
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return redirect(url_for("admin_dashboard"))

    has_orders = db.query(
        "SELECT COUNT(*) AS c FROM order_item WHERE product_id=?", (product_id,), one=True
    )["c"]
    if has_orders:
        flash(f"Không thể xoá vĩnh viễn \"{product['name']}\" vì sản phẩm đã có trong đơn hàng — hãy dùng Ẩn thay vì Xoá.")
        return redirect(url_for("admin_dashboard"))

    db.execute("DELETE FROM review WHERE product_id=?", (product_id,))
    db.execute("DELETE FROM product_variant WHERE product_id=?", (product_id,))
    db.execute("DELETE FROM product WHERE id=?", (product_id,))
    flash(f"Đã xoá vĩnh viễn sản phẩm \"{product['name']}\".")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/san-pham/<int:product_id>/danh-gia")
@admin_required
def admin_product_reviews(product_id):
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404
    reviews = get_reviews(product_id)
    return render_template("admin/product_reviews.html", product=product, reviews=reviews)


@app.route("/admin/san-pham/<int:product_id>/danh-gia/them", methods=["POST"])
@admin_required
def admin_review_add(product_id):
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404

    reviewer_name = request.form.get("reviewer_name", "").strip() or "Khách hàng"
    try:
        rating = max(1, min(5, int(request.form.get("rating", 5))))
    except (ValueError, TypeError):
        rating = 5
    comment = request.form.get("comment", "").strip()

    image_files = [f for f in request.files.getlist("images") if f and f.filename]
    saved_images = [pth for pth in (_save_uploaded_file(f) for f in image_files) if pth]
    images = ",".join(saved_images)

    video_path = _save_uploaded_video(request.files.get("video"))

    if reviewer_name and (comment or images or video_path):
        db.execute(
            """INSERT INTO review (product_id, reviewer_name, rating, comment, images, video_path)
               VALUES (?,?,?,?,?,?)""",
            (product_id, reviewer_name, rating, comment, images, video_path),
        )
    return redirect(url_for("admin_product_reviews", product_id=product_id))


@app.route("/admin/danh-gia/<int:review_id>/xoa")
@admin_required
def admin_review_delete(review_id):
    review = db.query("SELECT * FROM review WHERE id=?", (review_id,), one=True)
    if review:
        db.execute("DELETE FROM review WHERE id=?", (review_id,))
        return redirect(url_for("admin_product_reviews", product_id=review["product_id"]))
    return redirect(url_for("admin_dashboard"))


# ---------- Mô tả sản phẩm dạng khối (chữ + ảnh xen kẽ) ----------
@app.route("/admin/san-pham/<int:product_id>/mo-ta")
@admin_required
def admin_product_description(product_id):
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404
    blocks = get_description_blocks(product_id)
    return render_template("admin/product_description.html", product=product, blocks=blocks)


@app.route("/admin/san-pham/<int:product_id>/mo-ta/them", methods=["POST"])
@admin_required
def admin_description_block_add(product_id):
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404

    block_type = request.form.get("block_type", "text")
    content = request.form.get("content", "").strip() if block_type == "text" else None
    image_path = _save_uploaded_file(request.files.get("image")) if block_type == "image" else None

    if (block_type == "text" and content) or (block_type == "image" and image_path):
        max_order_row = db.query(
            "SELECT MAX(display_order) AS m FROM product_description_block WHERE product_id=?",
            (product_id,), one=True,
        )
        next_order = (max_order_row["m"] + 1) if max_order_row and max_order_row["m"] is not None else 0
        db.execute(
            """INSERT INTO product_description_block (product_id, block_type, content, image_path, display_order)
               VALUES (?,?,?,?,?)""",
            (product_id, block_type, content, image_path, next_order),
        )
    return redirect(url_for("admin_product_description", product_id=product_id))


@app.route("/admin/mo-ta/<int:block_id>/xoa")
@admin_required
def admin_description_block_delete(block_id):
    block = db.query("SELECT * FROM product_description_block WHERE id=?", (block_id,), one=True)
    if block:
        db.execute("DELETE FROM product_description_block WHERE id=?", (block_id,))
        return redirect(url_for("admin_product_description", product_id=block["product_id"]))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/mo-ta/<int:block_id>/di-chuyen/<direction>")
@admin_required
def admin_description_block_move(block_id, direction):
    block = db.query("SELECT * FROM product_description_block WHERE id=?", (block_id,), one=True)
    if not block:
        return redirect(url_for("admin_dashboard"))
    blocks = db.query(
        "SELECT * FROM product_description_block WHERE product_id=? ORDER BY display_order ASC, id ASC",
        (block["product_id"],),
    )
    ids = [b["id"] for b in blocks]
    if block_id in ids:
        idx = ids.index(block_id)
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(ids):
            a, b = blocks[idx], blocks[swap_idx]
            db.execute("UPDATE product_description_block SET display_order=? WHERE id=?", (b["display_order"], a["id"]))
            db.execute("UPDATE product_description_block SET display_order=? WHERE id=?", (a["display_order"], b["id"]))
    return redirect(url_for("admin_product_description", product_id=block["product_id"]))


# ---------- Ảnh riêng theo từng màu sắc ----------
@app.route("/admin/san-pham/<int:product_id>/anh-mau")
@admin_required
def admin_product_color_images(product_id):
    product = db.query("SELECT * FROM product WHERE id=?", (product_id,), one=True)
    if not product:
        return "Không tìm thấy sản phẩm", 404
    color_images = get_color_images(product_id)
    colors = [c.strip() for c in (product["colors"] or "").split(",") if c.strip()]
    return render_template(
        "admin/product_color_images.html", product=product, color_images=color_images, colors=colors,
    )


@app.route("/admin/san-pham/<int:product_id>/anh-mau/them", methods=["POST"])
@admin_required
def admin_color_image_add(product_id):
    color = request.form.get("color", "").strip()
    image_path = _save_uploaded_file(request.files.get("image"))
    if color and image_path:
        db.execute(
            """INSERT INTO product_color_image (product_id, color, image_path) VALUES (?,?,?)
               ON CONFLICT(product_id, color) DO UPDATE SET image_path=excluded.image_path""",
            (product_id, color, image_path),
        )
    return redirect(url_for("admin_product_color_images", product_id=product_id))


@app.route("/admin/anh-mau/<int:image_id>/xoa")
@admin_required
def admin_color_image_delete(image_id):
    row = db.query("SELECT * FROM product_color_image WHERE id=?", (image_id,), one=True)
    if row:
        db.execute("DELETE FROM product_color_image WHERE id=?", (image_id,))
        return redirect(url_for("admin_product_color_images", product_id=row["product_id"]))
    return redirect(url_for("admin_dashboard"))


# ---------- Trang chủ Shop + Trang trí Shop ----------
@app.route("/shop")
def shop_home():
    blocks = get_shop_blocks(active_only=True)
    featured_products = db.query(
        "SELECT * FROM product WHERE active=1 ORDER BY sold_count DESC LIMIT 10"
    )
    total_products = db.query("SELECT COUNT(*) AS c FROM product WHERE active=1", one=True)["c"]
    avg_rating_row = db.query("SELECT AVG(rating) AS a FROM product WHERE active=1", one=True)
    shop_rating = round(avg_rating_row["a"], 1) if avg_rating_row and avg_rating_row["a"] else 5.0
    total_sold = db.query("SELECT SUM(sold_count) AS s FROM product", one=True)["s"] or 0
    categories = db.query("SELECT * FROM category ORDER BY id")
    return render_template(
        "shop_home.html", blocks=blocks, featured_products=featured_products,
        total_products=total_products, shop_rating=shop_rating, total_sold=total_sold,
        categories=categories,
    )


@app.route("/admin/trang-tri-shop")
@admin_required
def admin_shop_decoration():
    blocks = get_shop_blocks(active_only=False)
    return render_template("admin/shop_decoration.html", blocks=blocks)


def _parse_aspect_ratio(form):
    preset = form.get("aspect_ratio_preset", "2:1")
    if preset == "custom":
        try:
            w = max(1, int(form.get("ratio_w") or 2))
            h = max(1, int(form.get("ratio_h") or 1))
        except (ValueError, TypeError):
            w, h = 2, 1
        return f"{w}:{h}"
    return preset


@app.route("/admin/trang-tri-shop/them", methods=["POST"])
@admin_required
def admin_shop_block_add():
    block_type = request.form.get("block_type", "banner_single")
    title = request.form.get("title", "").strip()
    subtitle = request.form.get("subtitle", "").strip()
    link_url = request.form.get("link_url", "").strip()
    aspect_ratio = _parse_aspect_ratio(request.form)

    image_files = [f for f in request.files.getlist("images") if f and f.filename]
    saved_images = [pth for pth in (_save_uploaded_file(f) for f in image_files) if pth]
    image_path = ",".join(saved_images)

    max_order_row = db.query("SELECT MAX(display_order) AS m FROM shop_page_block", one=True)
    next_order = (max_order_row["m"] + 1) if max_order_row and max_order_row["m"] is not None else 0

    db.execute(
        """INSERT INTO shop_page_block (block_type, title, subtitle, image_path, link_url, aspect_ratio, display_order, active)
           VALUES (?,?,?,?,?,?,?,1)""",
        (block_type, title, subtitle, image_path, link_url, aspect_ratio, next_order),
    )
    return redirect(url_for("admin_shop_decoration"))


@app.route("/admin/trang-tri-shop/<int:block_id>/xoa")
@admin_required
def admin_shop_block_delete(block_id):
    db.execute("DELETE FROM shop_page_block WHERE id=?", (block_id,))
    return redirect(url_for("admin_shop_decoration"))


@app.route("/admin/trang-tri-shop/<int:block_id>/an-hien")
@admin_required
def admin_shop_block_toggle(block_id):
    block = db.query("SELECT * FROM shop_page_block WHERE id=?", (block_id,), one=True)
    if block:
        db.execute("UPDATE shop_page_block SET active=? WHERE id=?", (0 if block["active"] else 1, block_id))
    return redirect(url_for("admin_shop_decoration"))


@app.route("/admin/trang-tri-shop/<int:block_id>/di-chuyen/<direction>")
@admin_required
def admin_shop_block_move(block_id, direction):
    blocks = db.query("SELECT * FROM shop_page_block ORDER BY display_order ASC, id ASC")
    ids = [b["id"] for b in blocks]
    if block_id in ids:
        idx = ids.index(block_id)
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(ids):
            a, b = blocks[idx], blocks[swap_idx]
            db.execute("UPDATE shop_page_block SET display_order=? WHERE id=?", (b["display_order"], a["id"]))
            db.execute("UPDATE shop_page_block SET display_order=? WHERE id=?", (a["display_order"], b["id"]))
    return redirect(url_for("admin_shop_decoration"))


# ---------- Quản trị Voucher (mã giảm giá) ----------
@app.route("/admin/voucher")
@admin_required
def admin_voucher_list():
    vouchers = db.query("SELECT * FROM voucher ORDER BY id DESC")
    products = db.query("SELECT id, name FROM product ORDER BY name")
    voucher_products = {}
    for v in vouchers:
        rows = db.query("SELECT product_id FROM voucher_product WHERE voucher_id=?", (v["id"],))
        voucher_products[v["id"]] = {r["product_id"] for r in rows}
    return render_template("admin/voucher_list.html", vouchers=vouchers, products=products,
                            voucher_products=voucher_products)


@app.route("/admin/voucher/them", methods=["POST"])
@admin_required
def admin_voucher_add():
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    discount_type = request.form.get("discount_type", "amount")
    try:
        discount_value = int(request.form.get("discount_value") or 0)
    except (ValueError, TypeError):
        discount_value = 0
    max_discount_amount = request.form.get("max_discount_amount") or None
    max_discount_amount = int(max_discount_amount) if max_discount_amount else None
    min_order_value = int(request.form.get("min_order_value") or 0)
    total_usage_limit = request.form.get("total_usage_limit") or None
    total_usage_limit = int(total_usage_limit) if total_usage_limit else None
    start_at = request.form.get("start_at") or None
    end_at = request.form.get("end_at") or None
    product_ids = [int(pid) for pid in request.form.getlist("product_ids") if pid]
    scope = "product" if product_ids else "shop"

    if not code or discount_value <= 0:
        flash("Vui lòng nhập Mã voucher và Mức giảm hợp lệ.")
        return redirect(url_for("admin_voucher_list"))

    existing = db.query("SELECT id FROM voucher WHERE code=?", (code,), one=True)
    if existing:
        flash(f"Mã voucher \"{code}\" đã tồn tại.")
        return redirect(url_for("admin_voucher_list"))

    voucher_id = db.execute(
        """INSERT INTO voucher (code, name, discount_type, discount_value, max_discount_amount,
           min_order_value, total_usage_limit, scope, start_at, end_at, active)
           VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
        (code, name, discount_type, discount_value, max_discount_amount,
         min_order_value, total_usage_limit, scope, start_at, end_at),
    )
    for pid in product_ids:
        db.execute("INSERT OR IGNORE INTO voucher_product (voucher_id, product_id) VALUES (?,?)", (voucher_id, pid))
    flash(f"Đã tạo mã voucher {code}.")
    return redirect(url_for("admin_voucher_list"))


@app.route("/admin/voucher/<int:voucher_id>/an-hien")
@admin_required
def admin_voucher_toggle(voucher_id):
    voucher = db.query("SELECT * FROM voucher WHERE id=?", (voucher_id,), one=True)
    if voucher:
        db.execute("UPDATE voucher SET active=? WHERE id=?", (0 if voucher["active"] else 1, voucher_id))
    return redirect(url_for("admin_voucher_list"))


@app.route("/admin/voucher/<int:voucher_id>/xoa")
@admin_required
def admin_voucher_delete(voucher_id):
    db.execute("DELETE FROM voucher_product WHERE voucher_id=?", (voucher_id,))
    db.execute("DELETE FROM voucher WHERE id=?", (voucher_id,))
    return redirect(url_for("admin_voucher_list"))


# ---------- Quản trị Combo Khuyến Mãi ----------
@app.route("/admin/combo")
@admin_required
def admin_combo_list():
    combos = db.query("SELECT * FROM combo_deal ORDER BY id DESC")
    products = db.query("SELECT id, name FROM product ORDER BY name")
    combo_products = {}
    for c in combos:
        rows = db.query("SELECT product_id FROM combo_deal_product WHERE combo_id=?", (c["id"],))
        combo_products[c["id"]] = {r["product_id"] for r in rows}
    return render_template("admin/combo_list.html", combos=combos, products=products,
                            combo_products=combo_products)


@app.route("/admin/combo/them", methods=["POST"])
@admin_required
def admin_combo_add():
    name = request.form.get("name", "").strip() or "Combo khuyến mãi"
    try:
        min_quantity = max(2, int(request.form.get("min_quantity") or 2))
        discount_amount = int(request.form.get("discount_amount") or 0)
    except (ValueError, TypeError):
        flash("Số lượng tối thiểu / mức giảm không hợp lệ.")
        return redirect(url_for("admin_combo_list"))
    product_ids = [int(pid) for pid in request.form.getlist("product_ids") if pid]
    scope = "product" if product_ids else "shop"

    if discount_amount <= 0:
        flash("Vui lòng nhập mức giảm hợp lệ.")
        return redirect(url_for("admin_combo_list"))

    combo_id = db.execute(
        """INSERT INTO combo_deal (name, min_quantity, discount_amount, scope, active)
           VALUES (?,?,?,?,1)""",
        (name, min_quantity, discount_amount, scope),
    )
    for pid in product_ids:
        db.execute("INSERT OR IGNORE INTO combo_deal_product (combo_id, product_id) VALUES (?,?)", (combo_id, pid))
    flash(f"Đã tạo combo \"{name}\".")
    return redirect(url_for("admin_combo_list"))


@app.route("/admin/combo/<int:combo_id>/an-hien")
@admin_required
def admin_combo_toggle(combo_id):
    combo = db.query("SELECT * FROM combo_deal WHERE id=?", (combo_id,), one=True)
    if combo:
        db.execute("UPDATE combo_deal SET active=? WHERE id=?", (0 if combo["active"] else 1, combo_id))
    return redirect(url_for("admin_combo_list"))


@app.route("/admin/combo/<int:combo_id>/xoa")
@admin_required
def admin_combo_delete(combo_id):
    db.execute("DELETE FROM combo_deal_product WHERE combo_id=?", (combo_id,))
    db.execute("DELETE FROM combo_deal WHERE id=?", (combo_id,))
    return redirect(url_for("admin_combo_list"))


# ---------- Quản trị Flash Sale (tối đa 10 sản phẩm / đợt) ----------
FLASH_SALE_MAX_ITEMS = 10


@app.route("/admin/flash-sale")
@admin_required
def admin_flash_sale_list():
    sales = db.query("SELECT * FROM flash_sale ORDER BY id DESC")
    sale_items = {s["id"]: get_flash_sale_items(s["id"]) for s in sales}
    products = db.query("SELECT id, name, price FROM product WHERE active=1 ORDER BY name")
    return render_template("admin/flash_sale_list.html", sales=sales, sale_items=sale_items,
                            products=products, max_items=FLASH_SALE_MAX_ITEMS)


@app.route("/admin/flash-sale/them", methods=["POST"])
@admin_required
def admin_flash_sale_add():
    name = request.form.get("name", "").strip() or "Flash Sale"
    start_at = request.form.get("start_at") or None
    end_at = request.form.get("end_at") or None
    if not start_at or not end_at:
        flash("Vui lòng chọn đầy đủ Thời gian bắt đầu và kết thúc.")
        return redirect(url_for("admin_flash_sale_list"))
    db.execute(
        "INSERT INTO flash_sale (name, start_at, end_at, active) VALUES (?,?,?,1)",
        (name, start_at, end_at),
    )
    flash(f"Đã tạo đợt Flash Sale \"{name}\".")
    return redirect(url_for("admin_flash_sale_list"))


@app.route("/admin/flash-sale/<int:sale_id>/an-hien")
@admin_required
def admin_flash_sale_toggle(sale_id):
    sale = db.query("SELECT * FROM flash_sale WHERE id=?", (sale_id,), one=True)
    if sale:
        db.execute("UPDATE flash_sale SET active=? WHERE id=?", (0 if sale["active"] else 1, sale_id))
    return redirect(url_for("admin_flash_sale_list"))


@app.route("/admin/flash-sale/<int:sale_id>/xoa")
@admin_required
def admin_flash_sale_delete(sale_id):
    db.execute("DELETE FROM flash_sale_item WHERE flash_sale_id=?", (sale_id,))
    db.execute("DELETE FROM flash_sale WHERE id=?", (sale_id,))
    return redirect(url_for("admin_flash_sale_list"))


@app.route("/admin/flash-sale/<int:sale_id>/san-pham/them", methods=["POST"])
@admin_required
def admin_flash_sale_item_add(sale_id):
    sale = db.query("SELECT * FROM flash_sale WHERE id=?", (sale_id,), one=True)
    if not sale:
        return redirect(url_for("admin_flash_sale_list"))

    current_count = db.query(
        "SELECT COUNT(*) AS c FROM flash_sale_item WHERE flash_sale_id=?", (sale_id,), one=True
    )["c"]
    product_id = request.form.get("product_id", type=int)
    already_in = db.query(
        "SELECT id FROM flash_sale_item WHERE flash_sale_id=? AND product_id=?", (sale_id, product_id), one=True
    )
    if not already_in and current_count >= FLASH_SALE_MAX_ITEMS:
        flash(f"Mỗi đợt Flash Sale chỉ được tối đa {FLASH_SALE_MAX_ITEMS} sản phẩm.")
        return redirect(url_for("admin_flash_sale_list"))

    try:
        sale_price = int(request.form.get("sale_price") or 0)
        stock_limit = int(request.form.get("stock_limit") or 0)
    except (ValueError, TypeError):
        flash("Giá sale / số lượng suất không hợp lệ.")
        return redirect(url_for("admin_flash_sale_list"))

    if not product_id or sale_price <= 0 or stock_limit <= 0:
        flash("Vui lòng chọn sản phẩm và nhập giá sale / số suất hợp lệ.")
        return redirect(url_for("admin_flash_sale_list"))

    db.execute(
        """INSERT INTO flash_sale_item (flash_sale_id, product_id, sale_price, stock_limit) VALUES (?,?,?,?)
           ON CONFLICT(flash_sale_id, product_id) DO UPDATE SET sale_price=excluded.sale_price, stock_limit=excluded.stock_limit""",
        (sale_id, product_id, sale_price, stock_limit),
    )
    return redirect(url_for("admin_flash_sale_list"))


@app.route("/admin/flash-sale/san-pham/<int:item_id>/xoa")
@admin_required
def admin_flash_sale_item_delete(item_id):
    db.execute("DELETE FROM flash_sale_item WHERE id=?", (item_id,))
    return redirect(url_for("admin_flash_sale_list"))


@app.route("/admin/don-hang")
@admin_required
def admin_orders():
    orders = db.query("SELECT * FROM orders ORDER BY id DESC")
    return render_template("admin/orders.html", orders=orders)


@app.route("/admin/don-hang/<int:order_id>")
@admin_required
def admin_order_detail(order_id):
    order = db.query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    items = db.query("SELECT * FROM order_item WHERE order_id=?", (order_id,))
    return render_template("admin/order_detail.html", order=order, items=items)


@app.route("/admin/don-hang/<int:order_id>/trang-thai", methods=["POST"])
@admin_required
def admin_order_status(order_id):
    status = request.form["status"]
    db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    return redirect(url_for("admin_order_detail", order_id=order_id))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
