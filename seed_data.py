# -*- coding: utf-8 -*-
"""
seed_data.py
------------
Dữ liệu sản phẩm THẬT được lấy trực tiếp từ trang Shopee VEQISTU
(https://shopee.vn/veqistu#product_list) ngày lấy dữ liệu, dùng để khởi tạo
catalog ban đầu cho web bán hàng riêng. Tên, giá, đánh giá, số lượng đã bán
là dữ liệu thật; chỉ có ẢNH sản phẩm là chưa có (dùng ô màu placeholder cho
tới khi bạn upload ảnh thật qua trang quản trị).
"""

CATEGORIES = [
    "Áo Polo độc quyền của nhà VEQISTU",
    "Áo Thun Trơn Form Boxy",
    "Áo Thun Baby Tee",
    "Áo Thun Form Boxy",
]

DEFAULT_COLORS = "Đen,Trắng,Xám"
DEFAULT_SIZES = "M,L,XL"

# (tên, giá, giá_gốc, danh_mục, rating, đã_bán, màu_placeholder)
PRODUCTS = [
    ("Áo Thun Big Boxy YOUTHPOWER IT'S SEA Form Rộng Nam Nữ Cổ Tròn Chất Liệu Cotton In Lụa Local Brand", 240000, None, "Áo Thun Form Boxy", 4.9, 0, "#2563eb"),
    ("UMEESAIGON Áo Thun Boxy \"Umee Letter\" Thun cotton Nam Nữ Cổ Tròn", 220000, None, "Áo Thun Form Boxy", 4.9, 0, "#dc2626"),
    ("Áo Thun Boxy MÈO HOA YOUTHPOWER Form Rộng Nam Nữ Oversize Unisex Cotton 2 Chiều 250gsm Cổ Tròn Local Brand Việt Nam", 250000, None, "Áo Thun Form Boxy", 4.9, 0, "#f59e0b"),
    ("Áo Thun Big Boxy YOUTHPOWER DUCK YEP Form Rộng Nam Nữ Cổ Tròn Chất Liệu Cotton In Lụa Local Brand", 250000, None, "Áo Thun Form Boxy", 4.9, 0, "#0891b2"),
    ("Áo thun boxy chill vibes 2104 HLFashion cổ tròn vải cotton 2c 250gsm đứng form in mix", 159000, None, "Áo Thun Form Boxy", 4.9, 0, "#16a34a"),
    ("Áo Thun Boxy VACA YOUTHPOWER Form Rộng Nam Nữ Oversize Unisex Cotton 2 Chiều 250gsm Cổ tròn Local Brand Việt Nam", 250000, None, "Áo Thun Form Boxy", 4.9, 0, "#7c3aed"),
    ("UMEESAIGON Áo Thun Big Boxy Form Rộng Tay Ngắn Cotton \"Sò + Dừa + Mattcha + Cá Heo\"", 220000, None, "Áo Thun Form Boxy", 4.9, 0, "#0d9488"),
    ("Áo Thun Boxy VIỆT NAM YOUTHPOWER Form Rộng Nam Nữ Oversize Unisex Cotton 2 Chiều 250gsm Cổ Tròn Local Brand Việt Nam", 250000, None, "Áo Thun Form Boxy", 4.9, 0, "#e11d48"),
    ("Áo Thun Boxy Đi Biển - MÙA HÈ - Premium Cotton 250gsm Cotton 2 Chiều Gimme - GMBX15", 129000, None, "Áo Thun Form Boxy", 4.9, 0, "#0284c7"),
    ("UMEESAIGON Áo Thun Boxy Tay Ngắn Cotton Cổ Tròn Nam Nữ \"MÈO NHỆN\"", 220000, None, "Áo Thun Form Boxy", 4.9, 0, "#4d7c0f"),
    ("Áo Thun Big Boxy YOUTHPOWER STARFISH Form Rộng Nam Nữ Cổ Tròn Chất Liệu Cotton In Lụa Local Brand", 250000, None, "Áo Thun Form Boxy", 4.9, 0, "#c026d3"),
    ("Áo Thun Boxy TROPICAL YOUTHPOWER Form Rộng Nam Nữ Oversize Unisex Cotton 2 Chiều 250gsm Cổ Tròn Local Brand Việt Nam", 144000, None, "Áo Thun Form Boxy", 4.9, 0, "#ea580c"),
    ("UMEESAIGON Áo Thun Big Boxy Form Rộng Tay Ngắn Cotton Cổ Tròn Nam Nữ \"MÈO RÂU\"", 220000, None, "Áo Thun Form Boxy", 4.9, 0, "#65a30d"),
    ("[MỞ BÁN] UMEESAIGON Áo Thun Form Boxy Tay Ngắn Cotton Cổ Tròn Nam Nữ \"UME SERAPHIC + UME MÈO NƠ ĐỎ\"", 220000, None, "Áo Thun Form Boxy", 4.9, 0, "#be123c"),
    ("Áo Thun Local Brand VEQISTU \"Thetees\" Form Big Boxy Unisex 250Gsm Cotton", 153124, 300000, "Áo Thun Form Boxy", 5.0, 2000, "#1d4ed8"),
    ("Áo Thun Local Brand VEQISTU \"Flower SS25\" Form Big Boxy Unisex 250Gsm Cotton", 201000, 300000, "Áo Thun Form Boxy", 4.9, 0, "#db2777"),
    ("Áo Thun BOXY Local Brand VEQISTU \"Only Members\" Áo Thun Boxy Form Rộng Unisex 250Gsm Cotton", 152688, 300000, "Áo Thun Form Boxy", 4.9, 6000, "#111827"),
    ("Áo Thun mùa hè Local Brand VEQISTU Earth, Áo Thun Boxy Form Rộng Unisex 250Gsm 100% Cotton", 201000, 300000, "Áo Thun Form Boxy", 5.0, 523, "#15803d"),
    ("Áo Thun Trơn Local Brand VEQISTU, Áo Thun Boxy Form Rộng Unisex 250Gsm 100% Cotton", 192923, 300000, "Áo Thun Trơn Form Boxy", 5.0, 283, "#374151"),
    ("Áo Thun Local Brand VEQISTU \"Service\" Form Big Boxy Unisex 250Gsm Cotton", 201000, 300000, "Áo Thun Form Boxy", 4.9, 0, "#9333ea"),
    ("Áo Thun Local Brand VEQISTU \"Đảo Cọ\" Form Big Boxy Unisex 250Gsm Cotton", 201000, 300000, "Áo Thun Form Boxy", 5.0, 273, "#0e7490"),
    ("Áo Thun Local Brand VEQISTU \"Xinh Như Hoa\", Áo Thun Boxy Form Rộng Unisex 250Gsm 100% Cotton", 201000, 300000, "Áo Thun Form Boxy", 4.9, 0, "#f43f5e"),
    ("Áo Thun Local Brand VEQISTU \"Quýt Làm Cam Chịu\", Áo Thun Boxy Form Rộng Unisex 250Gsm 100% Cotton", 164640, 300000, "Áo Thun Form Boxy", 4.9, 314, "#f97316"),
    ("Áo Thun Local Brand VEQISTU \"Tựa Bờ Vibe\", Áo Thun Boxy Form Rộng Unisex 250Gsm 100% Cotton", 201000, 300000, "Áo Thun Form Boxy", 5.0, 13, "#0369a1"),
    ("Áo Thun Big Boxy Local Brand VEQISTU Cotton Cổ Tròn Form Rộng Unisex Nam Nữ \"VEQISAIGON XXVIIIXX\" Oversize Streetwear", 201000, 300000, "Áo Thun Form Boxy", 5.0, 19, "#312e81"),
    ("Áo Thun Local Brand VEQISTU \"Vibes Japan\", Áo Thun Boxy Form Rộng Unisex 250Gsm 100% Cotton", 201000, 300000, "Áo Thun Form Boxy", 4.8, 53, "#7f1d1d"),
    ("Áo Thun Local Brand VEQISTU \"30 Tháng 4\" Form Big Boxy Rộng Unisex 250Gsm 100% Cotton", 201000, 300000, "Áo Thun Form Boxy", 5.0, 5, "#b91c1c"),
    ("Áo Thun Baby Tee Trơn VEQISTU, Áo Thun Trơn Nữ Local Brand 100% Cotton Premium Đã Xử Lý Co Rút", 201000, 300000, "Áo Thun Baby Tee", 4.9, 2000, "#be185d"),
    ("[VOUCHER 100K ĐỘC QUYỀN 06.06] Áo polo nam cao cấp BASIC, POLO QUỐC DÂN, sang trọng - VEQISTU", 300000, 400000, "Áo Polo độc quyền của nhà VEQISTU", 5.0, 4, "#1e3a8a"),
    ("Áo Thun Local Brand VEQISTU \"BST Trái Cây\", Form Boxy Rộng Unisex 250Gsm 100% Cotton", 201000, 300000, "Áo Thun Form Boxy", 4.6, 22, "#166534"),
]

COMMON_SPECS = {
    "material": "Cotton",
    "style": "Thể thao",
    "origin": "Việt Nam",
    "collar": "Cổ tròn",
}


def build_description(name):
    return (
        f"{name}.\n\n"
        "Chất liệu Cotton 250gsm 2 chiều, form rộng (boxy) thoải mái, "
        "phù hợp cả nam và nữ. Hàng local brand VEQISTU chính hãng.\n\n"
        "Hỗ trợ đổi size trong 15 ngày, bảo hành sản phẩm theo chính sách shop. "
        "Miễn phí vận chuyển toàn quốc."
    )
