"""拾光小店 - 一个用于 AI 冒烟测试演示的简单电商网站 (Flask)。

数据均为内存态, 无需数据库。账号: admin/admin123
"""
import uuid

from flask import (
    Flask, flash, redirect, render_template, request, session, url_for,
)

app = Flask(__name__)
app.secret_key = "dev-secret-for-smoke-test-demo"

# ---- 内存数据 -----------------------------------------------------------
USERS = {"admin": "admin123", "demo": "demo123"}

PRODUCTS = [
    {"id": 1, "name": "盲盒潮玩·星际漫游", "price": 79, "stock": 100},
    {"id": 2, "name": "陶瓷马克杯", "price": 49, "stock": 200},
    {"id": 3, "name": "帆布手账本", "price": 39, "stock": 150},
    {"id": 4, "name": "蓝牙音箱", "price": 199, "stock": 50},
    {"id": 5, "name": "无线充电宝", "price": 129, "stock": 80},
]

ORDERS = {}  # order_id -> {user, address, phone, items}


def get_cart() -> dict:
    return session.get("cart", {})


def find_product(product_id: int):
    return next((p for p in PRODUCTS if p["id"] == product_id), None)


# ---- 页面路由 -----------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username in USERS and USERS[username] == password:
            session["user"] = username
            return redirect(url_for("index"))
        error = "用户名或密码错误"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("cart", None)
    return redirect(url_for("index"))


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    product = find_product(product_id)
    if product is None:
        flash("商品不存在", "error")
        return redirect(url_for("index"))
    cart = get_cart()
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session["cart"] = cart
    return redirect(url_for("index"))


@app.route("/cart")
def cart():
    items = []
    total = 0
    for pid, qty in get_cart().items():
        product = find_product(int(pid))
        if product:
            subtotal = product["price"] * qty
            total += subtotal
            items.append({"product": product, "qty": qty, "subtotal": subtotal})
    return render_template("cart.html", items=items, total=total)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if "user" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        if not address or not phone:
            flash("请填写收货地址和联系电话", "error")
            return redirect(url_for("checkout"))
        order_id = "SO" + uuid.uuid4().hex[:8].upper()
        ORDERS[order_id] = {
            "user": session["user"],
            "address": address,
            "phone": phone,
            "items": get_cart(),
        }
        session.pop("cart", None)
        return redirect(url_for("order", order_id=order_id))
    return render_template("checkout.html")


@app.route("/order/<order_id>")
def order(order_id):
    info = ORDERS.get(order_id)
    if info is None:
        return "订单不存在", 404
    return render_template("order.html", order_id=order_id, info=info)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
