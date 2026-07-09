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
from functools import wraps

from flask import (
    Flask, redirect, render_template, request, session, url_for, flash, jsonify
)

import db
from seed_data import CATEGORIES, PRODUCTS, COMMON_SPECS, DEFAULT_COLORS, DEFAULT_SIZES, build_description

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "doi-chuoi-nay-truoc-khi-deploy-that")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # tối đa 15MB mỗi lần lưu sản phẩm (ảnh)

# ---------- Cấu hình upload ảnh sản phẩm ----------
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}


def _allowed_image(filename):
    return bool(filename) and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


def _save_uploaded_file(file_storage):
    """Lưu 1 file ảnh upload, trả về đường dẫn tương đối trong static/ (vd 'uploads/xxxx.jpg') hoặc None."""
    if not file_storage or not file_storage.filename or not _allowed_image(file_storage.filename):
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


def get_cart():
    return session.setdefault("cart", [])  # list of {product_id, name, price, variant, qty}


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
    return render_template("product_detail.html", p=product, related=related,
                            variants=variants, variants_json=variants_json)


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

    cart = get_cart()
    variant = f"{color} / {size}".strip(" /")
    for item in cart:
        if item["product_id"] == product_id and item["variant"] == variant:
            item["qty"] = min(item["qty"] + qty, max(available_stock, 1))
            break
    else:
        cart.append({
            "product_id": product_id, "name": product["name"], "price": unit_price,
            "variant": variant, "qty": min(qty, max(available_stock, 1)), "color_hex": product["color_hex"],
        })
    session.modified = True

    if request.form.get("buy_now"):
        return redirect(url_for("checkout"))
    return redirect(url_for("cart_view"))


@app.route("/cart")
def cart_view():
    cart = get_cart()
    return render_template("cart.html", cart=cart, total=cart_total(cart))


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

    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        address = request.form["address"].strip()
        payment_method = request.form["payment_method"]
        note = request.form.get("note", "").strip()

        if not (name and phone and address):
            flash("Vui lòng điền đầy đủ Họ tên, Số điện thoại và Địa chỉ.")
            return render_template("checkout.html", cart=cart, total=cart_total(cart))

        total = cart_total(cart)
        order_id = db.execute(
            """INSERT INTO orders (customer_name, phone, address, payment_method, total_amount, note)
               VALUES (?,?,?,?,?,?)""",
            (name, phone, address, payment_method, total, note),
        )
        for item in cart:
            db.execute(
                """INSERT INTO order_item (order_id, product_id, product_name, variant, unit_price, quantity)
                   VALUES (?,?,?,?,?,?)""",
                (order_id, item["product_id"], item["name"], item["variant"], item["price"], item["qty"]),
            )
        session["cart"] = []
        session.modified = True
        return redirect(url_for("order_success", order_id=order_id))

    return render_template("checkout.html", cart=cart, total=cart_total(cart))


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
        image_path, gallery_images, 1 if form.get("active") else 0,
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
               image_path=?, gallery_images=?, active=?,
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
               collar, colors, sizes, stock, description, color_hex, image_path, gallery_images, active,
               brand, pattern, season, sleeve_length, garment_length, fit,
               weight_grams, package_length_cm, package_width_cm, package_height_cm,
               ship_hoa_toc_enabled, ship_hoa_toc_fee, ship_nhanh_enabled, ship_nhanh_fee, is_preorder,
               rating, sold_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,5.0,0)""",
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
    db.execute("UPDATE product SET active=0 WHERE id=?", (product_id,))
    return redirect(url_for("admin_dashboard"))


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
