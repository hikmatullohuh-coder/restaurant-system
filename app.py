import os
import uuid
from functools import wraps
from datetime import datetime

import qrcode

from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    session
)

from supabase import create_client


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

def get_env_value(primary_name, fallback_name):
    """Read the configured value and ignore unresolved process.env placeholders."""
    primary_value = os.getenv(primary_name)
    fallback_value = os.getenv(fallback_name)

    if primary_value and not primary_value.startswith("process.env."):
        return primary_value
    if fallback_value and not fallback_value.startswith("process.env."):
        return fallback_value
    return primary_value or fallback_value


SUPABASE_URL = get_env_value("SUPABASE_URL_2", "SUPABASE_URL")
SUPABASE_SECRET_KEY = get_env_value("SUPABASE_SECRET_KEY_2", "SUPABASE_SECRET_KEY")
FLASK_SECRET_KEY = get_env_value("FLASK_SECRET_KEY_2", "FLASK_SECRET_KEY")


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL не найден в .env"
    )

if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY не найден в .env"
    )

if not FLASK_SECRET_KEY:
    raise RuntimeError(
        "FLASK_SECRET_KEY не найден в .env"
    )


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

app.secret_key = FLASK_SECRET_KEY

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Для HTTPS на Vercel позже можно включить:
# app.config["SESSION_COOKIE_SECURE"] = True


# =========================================================
# SUPABASE
# =========================================================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# =========================================================
# AUTH HELPERS
# =========================================================

def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    try:
        result = (
            supabase
            .table("profiles")
            .select("*")
            .eq("id", user_id)
            .eq("active", True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return None

        profile = result.data[0]

        return {
            "id": user_id,
            "full_name": profile.get(
                "full_name",
                ""
            ),
            "role": profile.get(
                "role"
            ),
            "active": profile.get(
                "active",
                True
            )
        }

    except Exception:
        return None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):

        user = get_current_user()

        if not user:
            return redirect(
                url_for("login")
            )

        return view(
            user=user,
            *args,
            **kwargs
        )

    return wrapped_view


def role_required(*allowed_roles):

    def decorator(view):

        @wraps(view)
        def wrapped_view(*args, **kwargs):

            user = get_current_user()

            if not user:
                return redirect(
                    url_for("login")
                )

            if user["role"] not in allowed_roles:
                return render_template(
                    "403.html",
                    user=user
                ), 403

            return view(
                user=user,
                *args,
                **kwargs
            )

        return wrapped_view

    return decorator


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "GET":

        if get_current_user():
            return redirect(
                url_for("home")
            )

        return render_template(
            "login.html"
        )

    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    if not email or not password:

        return render_template(
            "login.html",
            error="Введите email и пароль."
        )

    try:

        response = (
            supabase
            .auth
            .sign_in_with_password({
                "email": email,
                "password": password
            })
        )

        if not response.user:

            return render_template(
                "login.html",
                error="Не удалось выполнить вход."
            )

        session.clear()

        session["user_id"] = response.user.id

        if response.session:

            session["access_token"] = (
                response.session.access_token
            )

        user = get_current_user()

        if not user:

            session.clear()

            return render_template(
                "login.html",
                error=(
                    "Пользователь вошёл, "
                    "но профиль или роль "
                    "ещё не настроены."
                )
            )

        return redirect(
            url_for("home")
        )

    except Exception as error:

        print(
            "LOGIN ERROR:",
            error
        )

        return render_template(
            "login.html",
            error=f"Ошибка входа: {error}"
        )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
@role_required(
    "admin",
    "manager",
    "waiter",
    "cook",
    "cashier"
)
def home(user):

    try:

        orders_result = (
            supabase
            .table("orders")
            .select("*")
            .order(
                "created_at",
                desc=True
            )
            .limit(50)
            .execute()
        )

        orders = (
            orders_result.data
            or []
        )


        tables_result = (
            supabase
            .table("tables")
            .select("*")
            .order("number")
            .execute()
        )

        tables = (
            tables_result.data
            or []
        )


        total_revenue = sum(
            order.get("total", 0)
            for order in orders
            if order.get(
                "payment_status"
            ) == "paid"
        )


        order_count = len(
            orders
        )


        guests = sum(
            1
            for order in orders
            if order.get("status")
            != "cancelled"
        )


        average_check = (
            round(
                total_revenue
                / order_count
            )
            if order_count
            else 0
        )


        return render_template(
            "index.html",
            user=user,
            orders=orders,
            tables=tables,
            total_revenue=total_revenue,
            order_count=order_count,
            guests=guests,
            average_check=average_check
        )


    except Exception as error:

        return render_template(
            "403.html",
            user=user,
            error=str(error)
        ), 500


# =========================================================
# TABLES
# =========================================================

@app.route("/tables")
@role_required(
    "admin",
    "manager",
    "waiter"
)
def tables(user):

    result = (
        supabase
        .table("tables")
        .select("*")
        .order("number")
        .execute()
    )

    restaurant_tables = (
        result.data
        or []
    )


    return render_template(
        "tables.html",
        user=user,
        tables=restaurant_tables
    )


# =========================================================
# STAFF TABLE ORDER
# =========================================================

@app.route(
    "/table/<int:table_number>"
)
@role_required(
    "admin",
    "manager",
    "waiter"
)
def table_order(
    table_number,
    user
):

    table_result = (
        supabase
        .table("tables")
        .select("*")
        .eq(
            "number",
            table_number
        )
        .limit(1)
        .execute()
    )


    if not table_result.data:

        return "Стол не найден", 404


    menu_result = (
        supabase
        .table("menu_items")
        .select("*")
        .eq(
            "available",
            True
        )
        .order("category")
        .order("name")
        .execute()
    )


    return render_template(
        "table_order.html",
        user=user,
        table=table_result.data[0],
        table_id=table_number,
        menu=menu_result.data or []
    )


# =========================================================
# ADMIN MENU
# =========================================================

@app.route("/menu")
@role_required(
    "admin",
    "manager"
)
def menu_admin(user):

    result = (
        supabase
        .table("menu_items")
        .select("*")
        .order("category")
        .order("name")
        .execute()
    )


    menu = (
        result.data
        or []
    )


    categories = sorted(
        set(
            item["category"]
            for item in menu
        )
    )


    return render_template(
        "menu.html",
        user=user,
        menu=menu,
        categories=categories
    )


# =========================================================
# ADD MENU ITEM
# =========================================================

@app.route(
    "/menu/add",
    methods=["POST"]
)
@role_required(
    "admin",
    "manager"
)
def add_menu_item(user):

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


    try:

        price = int(
            price_raw
        )

    except ValueError:

        return redirect(
            url_for("menu_admin")
        )


    if (
        not name
        or not category
        or price <= 0
    ):

        return redirect(
            url_for("menu_admin")
        )


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


    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# UPDATE MENU
# =========================================================

@app.route(
    "/menu/<int:item_id>/update",
    methods=["POST"]
)
@role_required(
    "admin",
    "manager"
)
def update_menu_item(
    item_id,
    user
):

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
        request.form.get(
            "available"
        ) == "1"
    )


    try:

        price = int(
            price_raw
        )

    except ValueError:

        return redirect(
            url_for("menu_admin")
        )


    if (
        not name
        or not category
        or price <= 0
    ):

        return redirect(
            url_for("menu_admin")
        )


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
            "updated_at":
                datetime.now().isoformat()
        })
        .eq(
            "id",
            item_id
        )
        .execute()
    )


    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# DELETE MENU
# =========================================================

@app.route(
    "/menu/<int:item_id>/delete",
    methods=["POST"]
)
@role_required(
    "admin"
)
def delete_menu_item(
    item_id,
    user
):

    (
        supabase
        .table("menu_items")
        .delete()
        .eq(
            "id",
            item_id
        )
        .execute()
    )


    return redirect(
        url_for("menu_admin")
    )


# =========================================================
# QR GUEST PAGE
# =========================================================

@app.route(
    "/guest/<int:table_id>"
)
def guest_order(table_id):

    table_result = (
        supabase
        .table("tables")
        .select("*")
        .eq(
            "number",
            table_id
        )
        .limit(1)
        .execute()
    )


    if not table_result.data:

        return "Стол не найден", 404


    menu_result = (
        supabase
        .table("menu_items")
        .select("*")
        .eq(
            "available",
            True
        )
        .order("category")
        .order("name")
        .execute()
    )


    menu = (
        menu_result.data
        or []
    )


    categories = sorted(
        set(
            item["category"]
            for item in menu
        )
    )


    return render_template(
        "guest.html",
        table_id=table_id,
        table=table_result.data[0],
        menu=menu,
        categories=categories
    )


# =========================================================
# QR GENERATION
# =========================================================

@app.route(
    "/qr/<int:table_number>"
)
@role_required(
    "admin",
    "manager"
)
def qr_table(
    table_number,
    user
):

    table_result = (
        supabase
        .table("tables")
        .select("id,number")
        .eq(
            "number",
            table_number
        )
        .limit(1)
        .execute()
    )


    if not table_result.data:

        return "Стол не найден", 404


    os.makedirs(
        "static/qr",
        exist_ok=True
    )


    guest_url = url_for(
        "guest_order",
        table_id=table_number,
        _external=True
    )


    file_path = (
        "static/qr/"
        f"table_{table_number}.png"
    )


    qr = qrcode.make(
        guest_url
    )

    qr.save(file_path)


    return redirect(
        url_for("tables")
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


    table_result = (
        supabase
        .table("tables")
        .select("*")
        .eq(
            "number",
            table_number
        )
        .limit(1)
        .execute()
    )


    if not table_result.data:

        return jsonify({
            "success": False,
            "message":
                "Стол не найден."
        }), 404


    table = (
        table_result.data[0]
    )


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


        if (
            quantity <= 0
            or quantity > 50
        ):

            return jsonify({
                "success": False,
                "message":
                    "Некорректное количество."
            }), 400


        menu_result = (
            supabase
            .table("menu_items")
            .select("*")
            .eq(
                "id",
                item_id
            )
            .eq(
                "available",
                True
            )
            .limit(1)
            .execute()
        )


        if not menu_result.data:

            return jsonify({
                "success": False,
                "message":
                    "Блюдо недоступно."
            }), 400


        item = (
            menu_result.data[0]
        )


        line_total = (
            item["price"]
            * quantity
        )


        total += line_total


        prepared_items.append({
            "menu_item_id":
                item["id"],
            "name":
                item["name"],
            "price":
                item["price"],
            "quantity":
                quantity
        })


    public_id = (
        uuid.uuid4()
        .hex[:10]
        .upper()
    )


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


    order = (
        order_result.data[0]
    )


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


    (
        supabase
        .table("tables")
        .update({
            "status": "busy"
        })
        .eq(
            "id",
            table["id"]
        )
        .execute()
    )


    return jsonify({
        "success": True,
        "order_id":
            public_id,
        "total":
            total
    })


# =========================================================
# KITCHEN
# =========================================================

@app.route("/kitchen")
@role_required(
    "admin",
    "manager",
    "cook"
)
def kitchen(user):

    result = (
        supabase
        .table("orders")
        .select("*")
        .neq(
            "status",
            "completed"
        )
        .neq(
            "status",
            "cancelled"
        )
        .order(
            "created_at",
            desc=True
        )
        .execute()
    )


    orders = (
        result.data
        or []
    )


    for order in orders:

        items_result = (
            supabase
            .table("order_items")
            .select("*")
            .eq(
                "order_id",
                order["id"]
            )
            .order("id")
            .execute()
        )


        order["items"] = (
            items_result.data
            or []
        )


    return render_template(
        "kitchen.html",
        user=user,
        orders=orders
    )


# =========================================================
# ORDER STATUS
# =========================================================

@app.route(
    "/api/orders/<public_id>/status",
    methods=["POST"]
)
@role_required(
    "admin",
    "manager",
    "cook"
)
def update_order_status(
    public_id,
    user
):

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


    order_result = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "public_id",
            public_id
        )
        .limit(1)
        .execute()
    )


    if not order_result.data:

        return jsonify({
            "success": False,
            "message":
                "Заказ не найден."
        }), 404


    order = (
        order_result.data[0]
    )


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


    if order.get("table_id"):

        new_table_status = "busy"


        if status in {
            "served",
            "completed",
            "cancelled"
        }:

            new_table_status = "free"


        (
            supabase
            .table("tables")
            .update({
                "status":
                    new_table_status
            })
            .eq(
                "id",
                order["table_id"]
            )
            .execute()
        )


    return jsonify({
        "success":
            True
    })


# =========================================================
# RECEIPT
# =========================================================

@app.route(
    "/receipt/<public_id>"
)
def receipt(public_id):

    result = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "public_id",
            public_id
        )
        .limit(1)
        .execute()
    )


    if not result.data:

        return "Заказ не найден", 404


    order = (
        result.data[0]
    )


    items_result = (
        supabase
        .table("order_items")
        .select("*")
        .eq(
            "order_id",
            order["id"]
        )
        .order("id")
        .execute()
    )


    return render_template(
        "receipt.html",
        order=order,
        items=(
            items_result.data
            or []
        )
    )


# =========================================================
# PAYMENT PAGE
# =========================================================

@app.route(
    "/pay/<public_id>"
)
def pay(public_id):

    result = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "public_id",
            public_id
        )
        .limit(1)
        .execute()
    )


    if not result.data:

        return "Заказ не найден", 404


    return render_template(
        "receipt.html",
        order=result.data[0],
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


    result = (
        supabase
        .table("orders")
        .select("*")
        .eq(
            "public_id",
            public_id
        )
        .limit(1)
        .execute()
    )


    if not result.data:

        return jsonify({
            "success": False,
            "message":
                "Заказ не найден."
        }), 404


    order = (
        result.data[0]
    )


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
        "success":
            True
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    try:

        result = (
            supabase
            .table("menu_items")
            .select("id")
            .limit(1)
            .execute()
        )

        return jsonify({
            "status":
                "ok",

            "supabase":
                "connected"
        })


    except Exception as error:

        return jsonify({
            "status":
                "error",

            "message":
                str(error)
        }), 500


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000"))
    )
