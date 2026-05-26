from flask import Flask, render_template, request, redirect, url_for, session
from database.db import get_db, init_db, seed_db, get_user_by_email
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'dev-secret-key-change-in-production'  # In production, use environment variable


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "POST":
        # Get form data
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Validate input
        error = None
        if not name:
            error = "Name is required."
        elif not email:
            error = "Email is required."
        elif not password:
            error = "Password is required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters long."

        if error is None:
            # Check if email already exists
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            existing_user = cursor.fetchone()

            if existing_user:
                error = "Email already registered."
            else:
                # Create new user
                password_hash = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, password_hash)
                )
                db.commit()
                user_id = cursor.lastrowid

                # Log in the user (set session)
                session['user_id'] = user_id

                # Redirect to home page
                return redirect(url_for('landing'))

        # If we have an error, re-render the form with the error
        return render_template("register.html", error=error)

    # GET request: show the form
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("login.html", error="Email and password are required.")

        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("landing"))

        return render_template("login.html", error="Invalid email or password.")

    return render_template("login.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    # Hardcoded data for UI validation (Step 04)
    user = {
        "name": "Arjun Mehta",
        "email": "arjun.mehta@example.com",
        "member_since": "January 2024"
    }
    stats = {
        "total_spent": "₹42,500",
        "transaction_count": 128,
        "top_category": "Dining"
    }
    transactions = [
        {"date": "2026-05-20", "desc": "Starbucks Coffee", "cat": "Dining", "amt": 350},
        {"date": "2026-05-19", "desc": "Uber Ride", "cat": "Transport", "amt": 420},
        {"date": "2026-05-18", "desc": "Amazon Shopping", "cat": "Shopping", "amt": 2100},
        {"date": "2026-05-17", "desc": "Grocery Store", "cat": "Shopping", "amt": 1200},
        {"date": "2026-05-15", "desc": "Netflix Subscription", "cat": "Entertainment", "amt": 499},
    ]
    category_totals = [
        {"cat": "Dining", "amt": 12000, "pct": 28},
        {"cat": "Shopping", "amt": 15000, "pct": 35},
        {"cat": "Transport", "amt": 8000, "pct": 19},
        {"cat": "Entertainment", "amt": 7500, "pct": 18},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        category_totals=category_totals
    )



@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


# Initialize database on startup
with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
