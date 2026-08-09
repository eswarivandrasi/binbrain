from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "binbrain.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "binbrain_secret_key_2026"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        location TEXT NOT NULL,
        description TEXT,
        photo TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        waste_type TEXT NOT NULL,
        bin_type TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()


def current_user():
    return {
        "id": session.get("user_id"),
        "name": session.get("user_name", "Satya"),
        "email": session.get("user_email", "")
    }


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            return redirect("/dashboard")
        return render_template("login.html", error="Invalid email or password")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            return render_template("signup.html", error="Please fill all fields")
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (name,email,password) VALUES (?,?,?)",
                         (name, email, generate_password_hash(password)))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template("signup.html", error="Email already registered")
        conn.close()
        return redirect("/login")
    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    conn = get_db()
    scans = conn.execute("SELECT COUNT(*) c FROM scans").fetchone()["c"]
    reports = conn.execute("SELECT COUNT(*) c FROM reports").fetchone()["c"]
    recent_scans = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 3").fetchall()
    recent_reports = conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 2").fetchall()
    conn.close()
    stats = {"scans": scans or 42, "reports": reports or 250, "recycled": 25, "trees": 18, "points": 850}
    return render_template("dashboard.html", stats=stats, recent_scans=recent_scans, recent_reports=recent_reports)


@app.route("/scanner")
def scanner():
    return render_template("scanner.html")


@app.route("/scan", methods=["POST"])
def scan():
    image = request.files.get("image")
    filename = (image.filename if image else "").lower()
    if "food" in filename or "fruit" in filename or "vegetable" in filename or "organic" in filename:
        waste_type, bin_type = "Organic Waste", "Green Bin"
    elif "paper" in filename or "cardboard" in filename:
        waste_type, bin_type = "Paper", "Blue Bin"
    elif "metal" in filename or "can" in filename:
        waste_type, bin_type = "Metal", "Blue Bin"
    else:
        waste_type, bin_type = "Plastic Bottle", "Blue Bin"
    if image and image.filename:
        safe_name = os.path.basename(image.filename).replace(" ", "_")
        image.save(os.path.join(UPLOAD_DIR, safe_name))
    conn = get_db()
    conn.execute("INSERT INTO scans (user_id,waste_type,bin_type) VALUES (?,?,?)",
                 (session.get("user_id"), waste_type, bin_type))
    conn.commit(); conn.close()
    return jsonify({"waste_type": waste_type, "bin_type": bin_type})


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "POST":
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        photo = request.files.get("photo")
        if not location:
            return render_template("report.html", error="Please enter the garbage location")
        photo_name = ""
        if photo and photo.filename:
            photo_name = os.path.basename(photo.filename).replace(" ", "_")
            photo.save(os.path.join(UPLOAD_DIR, photo_name))
        conn = get_db()
        conn.execute("INSERT INTO reports (user_id,location,description,photo) VALUES (?,?,?,?)",
                     (session.get("user_id"), location, description, photo_name))
        conn.commit(); conn.close()
        return render_template("report.html", success=True)
    return render_template("report.html")


@app.route("/analytics")
def analytics():
    conn = get_db()
    counts = {}
    for row in conn.execute("SELECT waste_type, COUNT(*) c FROM scans GROUP BY waste_type"):
        counts[row["waste_type"]] = row["c"]
    report_count = conn.execute("SELECT COUNT(*) c FROM reports").fetchone()["c"]
    scan_count = conn.execute("SELECT COUNT(*) c FROM scans").fetchone()["c"]
    conn.close()
    return render_template("analytics.html", counts=counts, report_count=report_count, scan_count=scan_count)


@app.route("/rewards")
def rewards():
    return render_template("rewards.html")


@app.route("/admin")
def admin():
    conn = get_db()
    users = conn.execute("SELECT id,name,email FROM users ORDER BY id DESC").fetchall()
    reports = conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return render_template("admin.html", users=users, reports=reports)


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Image is too large. Maximum size is 8 MB."}), 413


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
