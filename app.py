from flask import Flask, render_template, request, redirect, session
import sqlite3, os
from datetime import datetime
from werkzeug.utils import secure_filename
import re

# ---------------- HELPERS ----------------
def normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = text.replace(" ", "")
    return text

app = Flask(__name__)
app.secret_key = "secret123"

DB_PATH = "complaints.db"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        phone TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        place TEXT,
        contact TEXT,
        complaint TEXT,
        civic TEXT,
        safety TEXT,
        priority TEXT,
        time TEXT,
        image TEXT,
        fake TEXT,
        resolution TEXT,
        status TEXT,
        solution TEXT
    )
    """)

    c.execute("INSERT OR IGNORE INTO users VALUES (NULL, ?, ?, ?)",
              ("admin", "admin@gmail.com", "9999999999"))

    c.execute("INSERT OR IGNORE INTO users VALUES (NULL, ?, ?, ?)",
              ("municipal", "municipal@gmail.com", "8888888888"))

    conn.commit()
    conn.close()


# ---------------- AI ----------------
fake_keywords = ["test", "fake", "demo", "nothing"]

high_keywords = ["gas", "fire", "electric", "shock", "danger", "manhole"]
medium_keywords = ["garbage", "drain", "pothole", "streetlight", "water"]

def detect_fake(desc):
    return "Fake" if any(w in desc.lower() for w in fake_keywords) else "Genuine"

def detect_priority(desc):
    desc = normalize(desc)

    if any(w in desc for w in ["gas","fire","danger","blast","accident","shock"]):
        return "High"
    elif any(w in desc for w in ["notworking","issue","broken","damage","leak"]):
        return "Medium"
    return "Low"

def detect_safety(desc):
    return "Yes" if any(w in desc.lower() for w in high_keywords) else "No"

def priority_by_category(civic):
    civic = normalize(civic)

    if any(w in civic for w in ["gas","fire","manhole","electric","sewage"]):
        return "High"
    elif any(w in civic for w in ["streetlight","pothole","garbage","water","traffic"]):
        return "Medium"
    return "Low"

def resolution_time(category):
    return {
        "Pothole": "3-5 Days",
        "Garbage": "1-2 Days",
        "Gas Leakage": "1 Day"
    }.get(category, "2-4 Days")


# ---------------- ROUTES ----------------

@app.route("/")
def home():
    if "role" not in session:
        return redirect("/login")

    if session["role"] == "user":
        return redirect("/submit")
    return redirect("/dashboard")


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        phone = request.form.get("phone")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name, phone FROM users WHERE email=? AND phone=?", (email, phone))
        user = c.fetchone()
        conn.close()

        if user:
            name, phone = user
            session["name"] = name
            session["phone"] = phone

            if email == "admin@gmail.com":
                session["role"] = "admin"
                return redirect("/dashboard")

            elif email == "municipal@gmail.com":
                session["role"] = "municipal"
                return redirect("/dashboard")

            else:
                session["role"] = "user"
                return redirect("/submit")

        return "Invalid Login"

    return render_template("login.html")


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (name,email,phone) VALUES (?,?,?)",
                      (name,email,phone))
            conn.commit()
        except:
            return "User already exists"

        conn.close()
        return redirect("/login")

    return render_template("signup.html")


# ---------- SUBMIT ----------
@app.route("/submit", methods=["GET","POST"])
def submit():
    if "role" not in session:
        return redirect("/login")

    if session["role"] != "user":
        return "Access Denied"

    if request.method == "POST":
        desc = request.form.get("complaint")
        place = request.form.get("place")
        civic = request.form.get("category")

        name = session["name"]
        contact = session["phone"]

        file = request.files.get("image")
        filename = ""

        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        priority = priority_by_category(civic)
        desc_priority = detect_priority(desc)
        safety = detect_safety(desc)

        if desc_priority == "High":
            priority = "High"
        elif desc_priority == "Medium" and priority != "High":
            priority = "Medium"

        if safety == "Yes":
            priority = "High"

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("""
        INSERT INTO complaints
        (name, place, contact, complaint, civic, safety, priority, time, image, fake, resolution, status, solution)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            name, place, contact, desc, civic,
            safety, priority,
            datetime.now().strftime("%d %b %Y %H:%M"),
            filename,
            detect_fake(desc),
            resolution_time(civic),
            "Pending",
            "Not Provided"
        ))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("submit.html",
                           name=session.get("name"),
                           role=session.get("role"))


# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "role" not in session:
        return redirect("/login")

    priority_filter = request.args.get("priority")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if priority_filter:
        c.execute("SELECT * FROM complaints WHERE priority=?", (priority_filter,))
    else:
        c.execute("SELECT * FROM complaints")

    data = c.fetchall()
    conn.close()

    return render_template("dashboard.html",
                           complaints=data,
                           role=session.get("role"),
                           name=session.get("name"))


# ---------- ACTIONS ----------
@app.route("/start/<int:id>", methods=["POST"])
def start(id):
    if session.get("role") not in ["admin","municipal"]:
        return "Access Denied"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE complaints SET status='In Progress' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/complete/<int:id>", methods=["POST"])
def complete(id):
    if session.get("role") not in ["admin","municipal"]:
        return "Access Denied"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE complaints SET status='Completed' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/solution/<int:id>", methods=["POST"])
def solution(id):
    if session.get("role") not in ["admin","municipal"]:
        return "Access Denied"

    sol = request.form.get("solution")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE complaints SET solution=?, status='Completed' WHERE id=?", (sol,id))
    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ---------- RUN ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)