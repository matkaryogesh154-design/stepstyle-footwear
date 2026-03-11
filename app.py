from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'shoe123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    price = db.Column(db.Float)
    category = db.Column(db.String(50))
    brand = db.Column(db.String(100))
    stock = db.Column(db.Integer)
    image_url = db.Column(db.String(300))
    description = db.Column(db.Text)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    items = db.Column(db.Text)
    total = db.Column(db.Float)
    status = db.Column(db.String(50), default='Pending')
    address = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)    


def get_cart():
    return session.get('cart', {})

def cart_count():
    return sum(i['qty'] for i in get_cart().values())

app.jinja_env.globals['cart_count'] = cart_count
import json as _json
app.jinja_env.filters['from_json'] = _json.loads

@app.route('/')
def index():
    products = Product.query.limit(8).all()
    ratings = {}
    for p in products:
        r = Rating.query.filter_by(product_id=p.id).all()
        ratings[p.id] = round(sum(x.stars for x in r) / len(r), 1) if r else 0
    return render_template('index.html', products=products, ratings=ratings)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            flash('Email already exists!', 'error')
            return redirect(url_for('register'))
        user = User(name=request.form['name'], email=request.form['email'],
                    password=generate_password_hash(request.form['password']))
        db.session.add(user)
        db.session.commit()
        flash('Registered! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['is_admin'] = user.is_admin
            return redirect(url_for('admin_dashboard') if user.is_admin else url_for('index'))
        flash('Wrong email or password!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/products')
def products():
    cat = request.args.get('category', '')
    search = request.args.get('search', '')
    query = Product.query
    if cat:
        query = query.filter_by(category=cat)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    items = query.all()
    ratings = {}
    for p in items:
        r = Rating.query.filter_by(product_id=p.id).all()
        ratings[p.id] = round(sum(x.stars for x in r) / len(r), 1) if r else 0
    return render_template('products.html', products=items,
                           selected=cat, search=search, ratings=ratings)

@app.route('/product/<int:id>')
def product_detail(id):
    product = Product.query.get_or_404(id)
    return render_template("product_detail.html", product=product)

@app.route('/search')
def search():
    query = request.args.get('q')
    products = Product.query.filter(Product.name.contains(query)).all()
    return render_template("products.html", products=products)

@app.route('/cart')
def cart():
    return render_template('cart.html', cart=get_cart())

@app.route('/add_cart/<int:pid>', methods=['POST'])
def add_cart(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    p = Product.query.get_or_404(pid)
    cart = get_cart()
    if str(pid) in cart:
        cart[str(pid)]['qty'] += 1
    else:
        cart[str(pid)] = {'id': pid, 'name': p.name, 'price': p.price,
                          'qty': 1, 'img': p.image_url}
    session['cart'] = cart
    flash('Added to cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/remove_cart/<int:pid>')
def remove_cart(pid):
    cart = get_cart()
    cart.pop(str(pid), None)
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cart = get_cart()
    if request.method == 'POST':
        total = sum(i['price'] * i['qty'] for i in cart.values())
        order = Order(user_id=session['user_id'],
                      items=json.dumps(list(cart.values())),
                      total=total, address=request.form['address'])
        db.session.add(order)
        db.session.commit()
        session['cart'] = {}
        flash('Order placed!', 'success')
        return redirect(url_for('my_orders'))
    return render_template('checkout.html', cart=cart)

@app.route('/orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    orders = Order.query.filter_by(user_id=session['user_id']).all()
    # Convert items to dict format
    import json as _json2
    for order in orders:
        items = _json2.loads(order.items)
        if isinstance(items, list):
            # list to dict convert karo
            items_dict = {}
            for item in items:
                items_dict[str(item.get('id', item['name']))] = item
            order.items = _json2.dumps(items_dict)
    return render_template('orders.html', orders=orders)

@app.route('/order/<int:id>')
def order_page(id):
    product = Product.query.get(id)
    return render_template("order.html", product=product)

@app.route('/place_order/<int:id>', methods=['POST'])
def place_order(id):

    quantity = request.form['quantity']
    address = request.form['address']

    order = Order(product_id=id, quantity=quantity, address=address)

    db.session.add(order)
    db.session.commit()

    return redirect('/orders')
    
@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_products=total_products,
                           total_orders=total_orders,
                           total_revenue=total_revenue)


@app.route('/admin/products')
def admin_products():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    return render_template('admin/products.html', products=Product.query.all())

@app.route('/admin/add', methods=['GET', 'POST'])
def admin_add():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        p = Product(name=request.form['name'],
                    price=float(request.form['price']),
                    category=request.form['category'],
                    brand=request.form['brand'],
                    stock=int(request.form['stock']),
                    image_url=request.form['image_url'],
                    description=request.form['description'])
        db.session.add(p)
        db.session.commit()
        flash('Product added!', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', product=None)

@app.route('/admin/edit/<int:pid>', methods=['GET', 'POST'])
def admin_edit(pid):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    p = Product.query.get_or_404(pid)
    if request.method == 'POST':
        p.name = request.form['name']
        p.price = float(request.form['price'])
        p.category = request.form['category']
        p.brand = request.form['brand']
        p.stock = int(request.form['stock'])
        p.image_url = request.form['image_url']
        p.description = request.form['description']
        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', product=p)

@app.route('/admin/delete/<int:pid>', methods=['POST'])
def admin_delete(pid):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    db.session.delete(Product.query.get_or_404(pid))
    db.session.commit()
    flash('Deleted!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
def admin_orders():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    orders = Order.query.order_by(Order.date.desc()).all()
    return render_template('admin/orders.html', orders=orders)

@app.route('/rate/<int:pid>', methods=['POST'])
def rate_product(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    stars = int(request.form.get('stars', 5))
    # Existing rating update karo
    existing = Rating.query.filter_by(
        user_id=session['user_id'], 
        product_id=pid
    ).first()
    if existing:
        existing.stars = stars
    else:
        rating = Rating(
            user_id=session['user_id'],
            product_id=pid,
            stars=stars
        )
        db.session.add(rating)
    db.session.commit()
    flash('Rating saved!', 'success')
    return redirect(url_for('products'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    orders = Order.query.filter_by(user_id=session['user_id']).all()
    total_spent = sum(o.total for o in orders)
    return render_template('profile.html', user=user, 
                           orders=orders, total_spent=total_spent)

@app.route('/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    user.name = request.form['name']
    new_password = request.form.get('new_password')
    if new_password:
        user.password = generate_password_hash(new_password)
    db.session.commit()
    session['user_name'] = user.name
    flash('Profile updated!', 'success')
    return redirect(url_for('profile'))
    

@app.route('/admin/status/<int:oid>', methods=['POST'])
def update_status(oid):
    o = Order.query.get_or_404(oid)
    o.status = request.form['status']
    db.session.commit()
    return redirect(url_for('admin_orders'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.first():
            admin = User(name='Admin', email='admin@shop.com',
                        password=generate_password_hash('admin123'),
                        is_admin=True)
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)