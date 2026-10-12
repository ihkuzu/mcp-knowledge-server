import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

FIRST = [
    "Anna",
    "Ben",
    "Clara",
    "David",
    "Emma",
    "Felix",
    "Greta",
    "Hannes",
    "Ida",
    "Jonas",
    "Klara",
    "Lukas",
    "Mia",
    "Noah",
    "Olivia",
    "Paul",
    "Rosa",
    "Sven",
    "Tina",
    "Uwe",
]
LAST = ["Becker", "Fischer", "Hoffmann", "Keller", "Lang", "Maier", "Neumann", "Richter", "Schulz", "Vogel"]
CITIES = ["Berlin", "Munich", "Hamburg", "Cologne", "Leipzig", "Nuremberg"]
PRODUCTS = [
    ("Laptop 14", "Computers", 899.0),
    ("Laptop 16", "Computers", 1299.0),
    ("Mini PC", "Computers", 349.0),
    ("Monitor 27", "Computers", 229.0),
    ("Mechanical Keyboard", "Accessories", 89.0),
    ("Wireless Mouse", "Accessories", 39.0),
    ("USB-C Hub", "Accessories", 45.0),
    ("Webcam HD", "Accessories", 59.0),
    ("Laptop Stand", "Accessories", 29.0),
    ("Headphones", "Audio", 149.0),
    ("Earbuds", "Audio", 79.0),
    ("Bluetooth Speaker", "Audio", 65.0),
    ("Microphone", "Audio", 119.0),
    ("Smartphone", "Mobile", 699.0),
    ("Tablet 10", "Mobile", 379.0),
    ("Phone Case", "Mobile", 19.0),
    ("Power Bank", "Mobile", 35.0),
    ("Smartwatch", "Mobile", 199.0),
]
STATUSES = ["delivered"] * 8 + ["cancelled", "returned"]

SCHEMA = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT, signup_date TEXT);
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                     order_date TEXT, status TEXT);
CREATE TABLE order_items (order_id INTEGER REFERENCES orders(id),
                          product_id INTEGER REFERENCES products(id), quantity INTEGER);
"""


def build_sample_db(path: str | Path, seed: int = 7) -> Path:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    if file.exists():
        file.unlink()
    rng = random.Random(seed)
    conn = sqlite3.connect(file)
    conn.executescript(SCHEMA)

    names = [f"{first} {last}" for first in FIRST for last in LAST]
    rng.shuffle(names)
    start = date(2024, 6, 1)
    customers = []
    for i in range(1, 61):
        signup = start + timedelta(days=rng.randrange(0, 500))
        customers.append((i, names[i - 1], rng.choice(CITIES), signup.isoformat()))
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
    conn.executemany(
        "INSERT INTO products VALUES (?, ?, ?, ?)",
        [(i, n, c, p) for i, (n, c, p) in enumerate(PRODUCTS, start=1)],
    )

    # only part of the customers order, so "never ordered" is a real question
    buyers = [c[0] for c in customers[:48]]
    orders, items = [], []
    for order_id in range(1, 401):
        day = date(2025, 1, 1) + timedelta(days=rng.randrange(0, 640))
        orders.append((order_id, rng.choice(buyers), day.isoformat(), rng.choice(STATUSES)))
        for product_id in rng.sample(range(1, len(PRODUCTS) + 1), rng.randint(1, 3)):
            items.append((order_id, product_id, rng.randint(1, 4)))
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
    conn.executemany("INSERT INTO order_items VALUES (?, ?, ?)", items)
    conn.commit()
    conn.close()
    return file
