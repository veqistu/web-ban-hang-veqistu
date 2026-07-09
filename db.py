"""
db.py
-----
Lớp truy cập cơ sở dữ liệu SQLite đơn giản (không dùng ORM để tránh phụ
thuộc thêm thư viện ngoài Flask). Toàn bộ dữ liệu sản phẩm/đơn hàng được
lưu bền vững trong file veqistu_shop.db (khác với bản demo Flash Sale
trước đây chỉ đọc CSV tĩnh).
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veqistu_shop.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS category (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES category(id),
    price INTEGER NOT NULL,
    original_price INTEGER,
    rating REAL DEFAULT 5.0,
    sold_count INTEGER DEFAULT 0,
    stock INTEGER DEFAULT 100,
    description TEXT,
    material TEXT,
    style TEXT,
    origin TEXT DEFAULT 'Việt Nam',
    collar TEXT,
    colors TEXT,
    sizes TEXT,
    color_hex TEXT DEFAULT '#ee4d2d',
    image_path TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    status TEXT DEFAULT 'Chờ xác nhận',
    total_amount INTEGER NOT NULL,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES product(id),
    product_name TEXT NOT NULL,
    variant TEXT,
    unit_price INTEGER NOT NULL,
    quantity INTEGER NOT NULL
);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def query(sql, params=(), one=False):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
