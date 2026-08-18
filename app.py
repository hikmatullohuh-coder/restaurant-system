from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
import uuid
from datetime import datetime

import qrcode


app = Flask(__name__)

DATABASE = "restaurant.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db()

    # Меню
    connection.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            emoji TEXT DEFAULT '🍽️',
            available INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # Заказы
    connection.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL UNIQUE,
            table_id INTEGER NOT NULL,
            customer_name TEXT,
            total INTEGER NOT NULL,
            status TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Блюда в заказах
    connection.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
    """)

    # Если меню пустое — создаём стартовые блюда
    menu_count = connection.execute("""
        SELECT COUNT(*) AS count
        FROM menu_items
    """).fetchone()["count"]

    if menu_count == 0:

        default_menu = [
            (
                "Тонкоцу Рамен",
                "Рамен",
                "Насыщенный бульон, лапша, яйцо и мясо",
                45000,
                "🍜"
            ),
            (
                "Суши-сет Sakura",
                "Суши",
                "Ассорти популярных суши",
                85000,
                "🍣"
            ),
            (
                "Якитори",
                "Горячее",
                "Курица на гриле с соусом",
                38000,
                "🍢"
            ),
            (
                "Удон",
                "Лапша",
                "Удон с овощами и специальным соусом",
                42000,
                "🍝"
            ),
            (
                "Гёдза",
                "Закуски",
                "Японские жареные пельмени",
                32000,
                "🥟"
            ),
            (
                "Матча Латте",
                "Напитки",
                "Нежный зелёный чай с молоком",
                25000,
                "🍵"
            )
        ]

        for item in default_menu:

            connection.execute("""
                INSERT INTO menu_items (
                    name,
                    category,
                    description,
                    price,
                    emoji,
                    available,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item[0],
                item[1],
                item[2],
                item[3],
                item[4],
                1,
                datetime.now().isoformat(timespec="seconds")
            ))

    connection.commit()
    connection.close()


# =========================================================
# MENU HELPERS
# =========================================================

def get_all_menu(include_unavailable=True):

    connection = get_db()

    if include_unavailable:
        items = connection.execute("""
            SELECT *
            FROM menu_items
            ORDER BY category, name
        """).fetchall()
    else:
        items = connection.execute("""
            SELECT *
            FROM menu_items
            WHERE available = 1
            ORDER BY category, name
        """).fetchall()

    connection.close()

    return items


def get_menu_item(item_id):

    connection = get_db()

    item = connection.execute("""
        SELECT *
        FROM menu_items
        WHERE id = ?
    """, (item_id,)).fetchone()

    connection.close()

    return item


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# TABLES
# =========================================================

@app.route("/tables")
def tables():
    return render_template("tables.html")


# =========================================================
# STAFF TABLE ORDER
# =========================================================

@app.route("/table/<int:table_id>")
def table_order(table_id):

    menu = get_all_menu(include_unavailable=False)

    return render_template(
        "table_order.html",
        table_id=table_id,
        menu=menu
    )


# =========================================================
# QR
# =========================================================

@app.route("/qr/<int:table_id>")
def qr_table(table_id):

    os.makedirs("static/qr", exist_ok=True)

    guest_url = url_for(
        "guest_order",
        table_id=table_id,
        _external=True
    )

    file_path = f"static/qr/table_{table_id}.png"

    qr = qrcode.make(guest_url)
    qr.save(file_path)

    return redirect(url_for("tables"))


# =========================================================
# GUEST QR MENU
# =========================================================

@app.route("/guest/<int:table_id>")
def guest_order(table_id):

    menu = get_all_menu(include_unavailable=False)

    categories = sorted(
        list(
            set(
                item["category"]
                for item in menu
            )
        )
    )

    return render_template(
        "guest.html",
        table_id=table_id,
        menu=menu,
        categories=categories
    )


# =========================================================
# ADMIN MENU
# =========================================================

@app.route("/menu")
def menu_admin():

    menu = get_all_menu()

    categories = sorted(
        list(
            set(
                item["category"]
                for item in menu
            )
        )
    )

    return render_template(
        "menu.html",
        menu=menu,
        categories=categories
    )


# =========================================================
# ADD MENU ITEM
# =========================================================

@app.route("/menu/add", methods=["POST"])
def add_menu_item():

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    price_raw = request.form.get("price", "").strip()
    emoji = request.form.get("emoji", "🍽️").strip()

    if not name or not category or not price_raw:

        return redirect(
            url_for("menu_admin")
        )

    try:
        price = int(price_raw)

    except ValueError:

        return redirect(
            url_for("menu_admin")
        )

    if price <= 0:
        return redirect(
            url_for("menu_admin")
        )

    connection = get_db()

    connection.execute("""
        INSERT INTO menu_items (
            name,
            category,
            description,
            price,
            emoji,
            available,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        category,
        description,
        price,
        emoji or "🍽️",
        1,
        datetime.now().isoformat(timespec="seconds")
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# UPDATE MENU ITEM
# =========================================================

@app.route("/menu/<int:item_id>/update", methods=["POST"])
def update_menu_item(item_id):

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    price_raw = request.form.get("price", "").strip()
    emoji = request.form.get("emoji", "🍽️").strip()

    available = 1 if request.form.get("available") == "1" else 0

    if not name or not category or not price_raw:

        return redirect(
            url_for("menu_admin")
        )

    try:
        price = int(price_raw)

    except ValueError:

        return redirect(
            url_for("menu_admin")
        )

    if price <= 0:
        return redirect(
            url_for("menu_admin")
        )

    connection = get_db()

    connection.execute("""
        UPDATE menu_items
        SET
            name = ?,
            category = ?,
            description = ?,
            price = ?,
            emoji = ?,
            available = ?
        WHERE id = ?
    """, (
        name,
        category,
        description,
        price,
        emoji or "🍽️",
        available,
        item_id
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# DELETE MENU ITEM
# =========================================================

@app.route("/menu/<int:item_id>/delete", methods=["POST"])
def delete_menu_item(item_id):

    connection = get_db()

    connection.execute("""
        DELETE FROM menu_items
        WHERE id = ?
    """, (item_id,))

    connection.commit()
    connection.close()

    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# CREATE ORDER
# =========================================================

@app.route("/api/orders", methods=["POST"])
def create_order():

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "success": False,
            "message": "Некорректные данные."
        }), 400

    table_id = data.get("table_id")
    customer_name = data.get("customer_name", "").strip()
    items = data.get("items", [])

    if not table_id:

        return jsonify({
            "success": False,
            "message": "Не указан столик."
        }), 400

    if not items:

        return jsonify({
            "success": False,
            "message": "Корзина пуста."
        }), 400

    prepared_items = []
    total = 0

    for cart_item in items:

        item_id = cart_item.get("id")

        try:
            quantity = int(
                cart_item.get("quantity", 0)
            )

        except (ValueError, TypeError):

            return jsonify({
                "success": False,
                "message": "Некорректное количество."
            }), 400

        menu_item = get_menu_item(item_id)

        if not menu_item:

            return jsonify({
                "success": False,
                "message": "Блюдо не найдено."
            }), 400

        if not menu_item["available"]:

            return jsonify({
                "success": False,
                "message":
                    f'Блюдо "{menu_item["name"]}" '
                    f'сейчас недоступно.'
            }), 400

        if quantity <= 0 or quantity > 50:

            return jsonify({
                "success": False,
                "message": "Некорректное количество блюда."
            }), 400

        item_total = (
            menu_item["price"] * quantity
        )

        total += item_total

        prepared_items.append({
            "name": menu_item["name"],
            "price": menu_item["price"],
            "quantity": quantity
        })

    public_id = uuid.uuid4().hex[:10].upper()

    created_at = datetime.now().isoformat(
        timespec="seconds"
    )

    connection = get_db()

    cursor = connection.execute("""
        INSERT INTO orders (
            public_id,
            table_id,
            customer_name,
            total,
            status,
            payment_status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        public_id,
        table_id,
        customer_name,
        total,
        "new",
        "unpaid",
        created_at
    ))

    order_id = cursor.lastrowid

    for item in prepared_items:

        connection.execute("""
            INSERT INTO order_items (
                order_id,
                name,
                price,
                quantity
            )
            VALUES (?, ?, ?, ?)
        """, (
            order_id,
            item["name"],
            item["price"],
            item["quantity"]
        ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True,
        "order_id": public_id,
        "total": total
    })


# =========================================================
# RECEIPT
# =========================================================

@app.route("/receipt/<public_id>")
def receipt(public_id):

    connection = get_db()

    order = connection.execute("""
        SELECT *
        FROM orders
        WHERE public_id = ?
    """, (public_id,)).fetchone()

    if not order:

        connection.close()

        return "Заказ не найден", 404

    items = connection.execute("""
        SELECT *
        FROM order_items
        WHERE order_id = ?
    """, (order["id"],)).fetchall()

    connection.close()

    return render_template(
        "receipt.html",
        order=order,
        items=items
    )


# =========================================================
# PAYMENT
# =========================================================

@app.route("/pay/<public_id>")
def pay(public_id):

    connection = get_db()

    order = connection.execute("""
        SELECT *
        FROM orders
        WHERE public_id = ?
    """, (public_id,)).fetchone()

    connection.close()

    if not order:

        return "Заказ не найден", 404

    return render_template(
        "receipt.html",
        order=order,
        items=[],
        payment_page=True
    )


# =========================================================
# DEMO PAYMENT
# =========================================================

@app.route("/api/payment/demo", methods=["POST"])
def demo_payment():

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "success": False
        }), 400

    public_id = data.get("order_id")

    if not public_id:

        return jsonify({
            "success": False
        }), 400

    connection = get_db()

    connection.execute("""
        UPDATE orders
        SET
            payment_status = ?,
            status = ?
        WHERE public_id = ?
    """, (
        "paid",
        "confirmed",
        public_id
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================================================
# KITCHEN
# =========================================================

@app.route("/kitchen")
def kitchen():

    connection = get_db()

    orders = connection.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
    """).fetchall()

    connection.close()

    return render_template(
        "kitchen.html",
        orders=orders
    )


# =========================================================
# ORDER STATUS
# =========================================================

@app.route(
    "/api/orders/<public_id>/status",
    methods=["POST"]
)
def update_order_status(public_id):

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "success": False
        }), 400

    status = data.get("status")

    allowed_statuses = {
        "new",
        "cooking",
        "ready",
        "served",
        "cancelled",
        "confirmed"
    }

    if status not in allowed_statuses:

        return jsonify({
            "success": False,
            "message": "Недопустимый статус."
        }), 400

    connection = get_db()

    connection.execute("""
        UPDATE orders
        SET status = ?
        WHERE public_id = ?
    """, (
        status,
        public_id
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )