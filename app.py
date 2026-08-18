import os
import uuid
from datetime import datetime

import qrcode
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify
)
from supabase import create_client


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL не найден в .env")

if not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY не найден в .env")


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# =========================================================
# HELPERS
# =========================================================

def format_error(error):
    return str(error)


def get_menu(include_unavailable=True):
    """
    Получает меню из Supabase.
    """

    query = (
        supabase
        .table("menu_items")
        .select("*")
        .order("category")
        .order("name")
    )

    if not include_unavailable:
        query = query.eq("available", True)

    result = query.execute()

    return result.data or []


def get_menu_item(item_id):
    """
    Получает одно блюдо.
    """

    result = (
        supabase
        .table("menu_items")
        .select("*")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_table_by_number(table_number):
    """
    Получает стол по его номеру.
    """

    result = (
        supabase
        .table("tables")
        .select("*")
        .eq("number", table_number)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_order_by_public_id(public_id):
    """
    Получает заказ.
    """

    result = (
        supabase
        .table("orders")
        .select("*")
        .eq("public_id", public_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    return result.data[0]


def get_order_items(order_id):
    """
    Получает блюда заказа.
    """

    result = (
        supabase
        .table("order_items")
        .select("*")
        .eq("order_id", order_id)
        .order("id")
        .execute()
    )

    return result.data or []


def update_table_status(table_id, status):
    """
    Меняет статус стола.
    """

    (
        supabase
        .table("tables")
        .update({
            "status": status
        })
        .eq("id", table_id)
        .execute()
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    try:
        menu = get_menu(include_unavailable=False)

        orders_result = (
            supabase
            .table("orders")
            .select("*")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )

        orders = orders_result.data or []

        tables_result = (
            supabase
            .table("tables")
            .select("*")
            .order("number")
            .execute()
        )

        tables = tables_result.data or []

        total_revenue = sum(
            order["total"]
            for order in orders
            if order.get("payment_status") == "paid"
        )

        order_count = len(orders)

        guests = sum(
            1
            for order in orders
            if order.get("status") != "cancelled"
        )

        average_check = (
            round(total_revenue / order_count)
            if order_count
            else 0
        )

        return render_template(
            "index.html",
            menu=menu,
            orders=orders,
            tables=tables,
            total_revenue=total_revenue,
            order_count=order_count,
            guests=guests,
            average_check=average_check
        )

    except Exception as error:

        return f"""
        <h1>Ошибка подключения к Supabase</h1>
        <p>{format_error(error)}</p>
        """, 500


# =========================================================
# TABLES
# =========================================================

@app.route("/tables")
def tables():

    try:

        result = (
            supabase
            .table("tables")
            .select("*")
            .order("number")
            .execute()
        )

        restaurant_tables = result.data or []

        return render_template(
            "tables.html",
            tables=restaurant_tables
        )

    except Exception as error:

        return f"""
        <h1>Ошибка загрузки столиков</h1>
        <p>{format_error(error)}</p>
        """, 500


# =========================================================
# TABLE ORDER FOR STAFF
# =========================================================

@app.route("/table/<int:table_number>")
def table_order(table_number):

    table = get_table_by_number(table_number)

    if not table:
        return "Стол не найден", 404

    menu = get_menu(include_unavailable=False)

    return render_template(
        "table_order.html",
        table_id=table_number,
        table=table,
        menu=menu
    )


# =========================================================
# QR CODE
# =========================================================

@app.route("/qr/<int:table_number>")
def qr_table(table_number):

    table = get_table_by_number(table_number)

    if not table:
        return "Стол не найден", 404

    os.makedirs("static/qr", exist_ok=True)

    guest_url = url_for(
        "guest_order",
        table_id=table_number,
        _external=True
    )

    file_path = (
        f"static/qr/table_{table_number}.png"
    )

    qr = qrcode.make(guest_url)
    qr.save(file_path)

    return redirect(
        url_for("tables")
    )


# =========================================================
# GUEST QR MENU
# =========================================================

@app.route("/guest/<int:table_id>")
def guest_order(table_id):

    table = get_table_by_number(table_id)

    if not table:
        return "Стол не найден", 404

    menu = get_menu(include_unavailable=False)

    categories = sorted(
        set(
            item["category"]
            for item in menu
        )
    )

    return render_template(
        "guest.html",
        table_id=table_id,
        table=table,
        menu=menu,
        categories=categories
    )


# =========================================================
# ADMIN MENU
# =========================================================

@app.route("/menu")
def menu_admin():

    try:

        menu = get_menu(
            include_unavailable=True
        )

        categories = sorted(
            set(
                item["category"]
                for item in menu
            )
        )

        return render_template(
            "menu.html",
            menu=menu,
            categories=categories
        )

    except Exception as error:

        return f"""
        <h1>Ошибка загрузки меню</h1>
        <p>{format_error(error)}</p>
        """, 500


# =========================================================
# ADD MENU ITEM
# =========================================================

@app.route("/menu/add", methods=["POST"])
def add_menu_item():

    name = request.form.get(
        "name",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    price_raw = request.form.get(
        "price",
        ""
    ).strip()

    emoji = request.form.get(
        "emoji",
        "🍽️"
    ).strip()


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


    try:

        (
            supabase
            .table("menu_items")
            .insert({
                "name": name,
                "category": category,
                "description": description,
                "price": price,
                "emoji": emoji or "🍽️",
                "available": True
            })
            .execute()
        )

    except Exception as error:

        return f"""
        <h1>Ошибка добавления блюда</h1>
        <p>{format_error(error)}</p>
        """, 500


    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# UPDATE MENU ITEM
# =========================================================

@app.route(
    "/menu/<int:item_id>/update",
    methods=["POST"]
)
def update_menu_item(item_id):

    name = request.form.get(
        "name",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    price_raw = request.form.get(
        "price",
        ""
    ).strip()

    emoji = request.form.get(
        "emoji",
        "🍽️"
    ).strip()

    available = (
        request.form.get("available")
        == "1"
    )


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


    try:

        (
            supabase
            .table("menu_items")
            .update({
                "name": name,
                "category": category,
                "description": description,
                "price": price,
                "emoji": emoji or "🍽️",
                "available": available,
                "updated_at": datetime.now().isoformat()
            })
            .eq("id", item_id)
            .execute()
        )

    except Exception as error:

        return f"""
        <h1>Ошибка изменения блюда</h1>
        <p>{format_error(error)}</p>
        """, 500


    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# DELETE MENU ITEM
# =========================================================

@app.route(
    "/menu/<int:item_id>/delete",
    methods=["POST"]
)
def delete_menu_item(item_id):

    try:

        (
            supabase
            .table("menu_items")
            .delete()
            .eq("id", item_id)
            .execute()
        )

    except Exception as error:

        return f"""
        <h1>Ошибка удаления блюда</h1>
        <p>{format_error(error)}</p>
        """, 500


    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# CREATE ORDER
# =========================================================

@app.route(
    "/api/orders",
    methods=["POST"]
)
def create_order():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message":
                "Некорректные данные."
        }), 400


    table_number = data.get(
        "table_id"
    )

    customer_name = data.get(
        "customer_name",
        ""
    ).strip()

    items = data.get(
        "items",
        []
    )

    source = data.get(
        "source",
        "staff"
    )


    if source not in {
        "staff",
        "qr"
    }:

        source = "staff"


    if not table_number:

        return jsonify({
            "success": False,
            "message":
                "Не указан столик."
        }), 400


    table = get_table_by_number(
        table_number
    )

    if not table:

        return jsonify({
            "success": False,
            "message":
                "Столик не найден."
        }), 404


    if not items:

        return jsonify({
            "success": False,
            "message":
                "Корзина пуста."
        }), 400


    prepared_items = []

    total = 0


    for cart_item in items:

        item_id = cart_item.get(
            "id"
        )


        try:

            quantity = int(
                cart_item.get(
                    "quantity",
                    0
                )
            )

        except (
            ValueError,
            TypeError
        ):

            return jsonify({
                "success": False,
                "message":
                    "Некорректное количество."
            }), 400


        if quantity <= 0 or quantity > 50:

            return jsonify({
                "success": False,
                "message":
                    "Некорректное количество."
            }), 400


        menu_item = get_menu_item(
            item_id
        )


        if not menu_item:

            return jsonify({
                "success": False,
                "message":
                    "Блюдо не найдено."
            }), 400


        if not menu_item["available"]:

            return jsonify({
                "success": False,
                "message":
                    f'Блюдо "{menu_item["name"]}" '
                    f'сейчас недоступно.'
            }), 400


        item_total = (
            menu_item["price"]
            * quantity
        )

        total += item_total


        prepared_items.append({
            "menu_item_id":
                menu_item["id"],

            "name":
                menu_item["name"],

            "price":
                menu_item["price"],

            "quantity":
                quantity
        })


    public_id = (
        uuid.uuid4()
        .hex[:10]
        .upper()
    )


    # -----------------------------------------
    # CREATE ORDER
    # -----------------------------------------

    order_result = (
        supabase
        .table("orders")
        .insert({
            "public_id":
                public_id,

            "table_id":
                table["id"],

            "customer_name":
                customer_name,

            "source":
                source,

            "total":
                total,

            "status":
                "new",

            "payment_status":
                "unpaid"
        })
        .execute()
    )


    if not order_result.data:

        return jsonify({
            "success": False,
            "message":
                "Не удалось создать заказ."
        }), 500


    order = order_result.data[0]


    # -----------------------------------------
    # CREATE ORDER ITEMS
    # -----------------------------------------

    order_items = []


    for item in prepared_items:

        order_items.append({

            "order_id":
                order["id"],

            "menu_item_id":
                item["menu_item_id"],

            "name":
                item["name"],

            "price":
                item["price"],

            "quantity":
                item["quantity"]
        })


    (
        supabase
        .table("order_items")
        .insert(order_items)
        .execute()
    )


    # -----------------------------------------
    # TABLE → BUSY
    # -----------------------------------------

    update_table_status(
        table["id"],
        "busy"
    )


    return jsonify({

        "success": True,

        "order_id":
            public_id,

        "total":
            total
    })


# =========================================================
# RECEIPT
# =========================================================

@app.route(
    "/receipt/<public_id>"
)
def receipt(public_id):

    order = get_order_by_public_id(
        public_id
    )

    if not order:
        return "Заказ не найден", 404


    items = get_order_items(
        order["id"]
    )


    return render_template(
        "receipt.html",
        order=order,
        items=items
    )


# =========================================================
# PAYMENT PAGE
# =========================================================

@app.route(
    "/pay/<public_id>"
)
def pay(public_id):

    order = get_order_by_public_id(
        public_id
    )

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

@app.route(
    "/api/payment/demo",
    methods=["POST"]
)
def demo_payment():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False
        }), 400


    public_id = data.get(
        "order_id"
    )


    if not public_id:

        return jsonify({
            "success": False
        }), 400


    order = get_order_by_public_id(
        public_id
    )


    if not order:

        return jsonify({
            "success": False,
            "message":
                "Заказ не найден."
        }), 404


    # -----------------------------------------
    # UPDATE ORDER
    # -----------------------------------------

    (
        supabase
        .table("orders")
        .update({
            "payment_status":
                "paid",

            "status":
                "confirmed",

            "updated_at":
                datetime.now().isoformat()
        })
        .eq(
            "id",
            order["id"]
        )
        .execute()
    )


    # -----------------------------------------
    # CREATE PAYMENT RECORD
    # -----------------------------------------

    (
        supabase
        .table("payments")
        .insert({
            "order_id":
                order["id"],

            "provider":
                "demo",

            "provider_payment_id":
                uuid.uuid4().hex,

            "amount":
                order["total"],

            "status":
                "paid"
        })
        .execute()
    )


    return jsonify({
        "success": True
    })


# =========================================================
# KITCHEN
# =========================================================

@app.route("/kitchen")
def kitchen():

    try:

        result = (
            supabase
            .table("orders")
            .select("*")
            .neq("status", "completed")
            .neq("status", "cancelled")
            .order("created_at", desc=True)
            .execute()
        )

        orders = result.data or []


        for order in orders:

            order["items"] = get_order_items(
                order["id"]
            )


        return render_template(
            "kitchen.html",
            orders=orders
        )


    except Exception as error:

        return f"""
        <h1>Ошибка кухни</h1>
        <p>{format_error(error)}</p>
        """, 500


# =========================================================
# UPDATE ORDER STATUS
# =========================================================

@app.route(
    "/api/orders/<public_id>/status",
    methods=["POST"]
)
def update_order_status(public_id):

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({
            "success": False
        }), 400


    status = data.get(
        "status"
    )


    allowed_statuses = {
        "new",
        "accepted",
        "cooking",
        "ready",
        "served",
        "cancelled",
        "completed",
        "confirmed"
    }


    if status not in allowed_statuses:

        return jsonify({

            "success": False,

            "message":
                "Недопустимый статус."

        }), 400


    order = get_order_by_public_id(
        public_id
    )


    if not order:

        return jsonify({

            "success": False,

            "message":
                "Заказ не найден."

        }), 404


    (
        supabase
        .table("orders")
        .update({
            "status":
                status,

            "updated_at":
                datetime.now().isoformat()
        })
        .eq(
            "id",
            order["id"]
        )
        .execute()
    )


    # -----------------------------------------
    # TABLE STATUS
    # -----------------------------------------

    if status in {
        "new",
        "accepted",
        "cooking",
        "ready",
        "confirmed"
    }:

        if order["table_id"]:

            update_table_status(
                order["table_id"],
                "busy"
            )


    elif status in {
        "served",
        "completed"
    }:

        if order["table_id"]:

            update_table_status(
                order["table_id"],
                "free"
            )


    elif status == "cancelled":

        if order["table_id"]:

            update_table_status(
                order["table_id"],
                "free"
            )


    return jsonify({
        "success": True
    })


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )