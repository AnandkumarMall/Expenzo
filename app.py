from flask import Flask, render_template, request, redirect, url_for, session
from database.db import (
    get_db, init_db, seed_db, get_user_by_email,
    get_user_by_id, get_expenses_for_user, count_expenses_for_user,
    get_total_spent, get_top_category, get_category_breakdown,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'dev-secret-key-change-in-production'  # In production, use environment variable


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def format_inr(amount):
    """Format a numeric amount as a thousands-separated string prefixed with the rupee glyph."""
    return f"₹{int(round(amount)):,}"


def format_member_since(iso_datetime):
    """Convert a users.created_at string (e.g. '2024-01-15 12:34:56') to 'January 2024'."""
    try:
        return datetime.strptime(iso_datetime, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")
    except (ValueError, TypeError):
        return iso_datetime


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

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)
    if user_row is None:
        # Stale session: user no longer exists in the database
        session.pop("user_id", None)
        return redirect(url_for("login"))

    total_spent = get_total_spent(user_id)
    top_category = get_top_category(user_id)
    stats = {
        "total_spent": format_inr(total_spent),
        "transaction_count": count_expenses_for_user(user_id),
        "top_category": top_category if top_category else "—",
    }
    category_totals = [
        {"cat": c, "amt": a, "pct": p}
        for c, a, p in get_category_breakdown(user_id)
    ]

    transactions = [
        {"date": r["date"], "desc": r["description"] or "", "cat": r["category"], "amt": r["amount"]}
        for r in get_expenses_for_user(user_id, limit=5)
    ]

    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "member_since": format_member_since(user_row["created_at"]),
    }

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        category_totals=category_totals,
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
