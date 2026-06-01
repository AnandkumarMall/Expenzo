from flask import Flask, render_template, request, redirect, url_for, session
from database.db import (
    get_db, init_db, seed_db, get_user_by_email,
    get_user_by_id, get_expenses_for_user, count_expenses_for_user,
    get_total_spent, get_top_category, get_category_breakdown,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta

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

    # Resolve the optional date filter from the query string. Invalid input
    # silently falls back to lifetime (None, None).
    date_from, date_to, active_preset = _resolve_date_range()
    active_filter = (
        {"from": date_from, "to": date_to, "preset": active_preset}
        if date_from and date_to
        else None
    )

    total_spent = get_total_spent(user_id, date_from, date_to)
    top_category = get_top_category(user_id, date_from, date_to)
    stats = {
        "total_spent": format_inr(total_spent),
        "transaction_count": count_expenses_for_user(user_id, date_from, date_to),
        "top_category": top_category if top_category else "—",
    }
    category_totals = [
        {"cat": c, "amt": a, "pct": p}
        for c, a, p in get_category_breakdown(user_id, date_from, date_to)
    ]

    transactions = [
        {"date": r["date"], "desc": r["description"] or "", "cat": r["category"], "amt": r["amount"]}
        for r in get_expenses_for_user(user_id, limit=5, date_from=date_from, date_to=date_to)
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
        active_filter=active_filter,
    )


# ------------------------------------------------------------------ #
# Profile filter helpers                                              #
# ------------------------------------------------------------------ #

def _today():
    """Return the server's "today" as a `date`. Indirected through a module
    helper so tests can monkey-patch the value without touching the immutable
    built-in `datetime.date` type.
    """
    return date.today()


def _shift_month(d, delta):
    """Return the first-of-month `delta` months from `d` (d must be day=1)."""
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _resolve_date_range():
    """Return (date_from, date_to, preset_label) for the current request.

    The preset label is one of the five preset names or None for lifetime.
    Invalid input (unknown preset, malformed dates, from > to) silently
    falls back to lifetime — see spec §"Query parameter contract" for the
    full rules.
    """
    preset = request.args.get("range")
    today = _today()

    if preset == "this_month":
        first = today.replace(day=1)
        return first.isoformat(), today.isoformat(), "this_month"
    if preset == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat(), "last_month"
    if preset == "last_3_months":
        first_this = today.replace(day=1)
        first = _shift_month(first_this, -2)
        return first.isoformat(), today.isoformat(), "last_3_months"
    if preset == "last_6_months":
        first_this = today.replace(day=1)
        first = _shift_month(first_this, -5)
        return first.isoformat(), today.isoformat(), "last_6_months"

    # Custom range: honour ?from=&to= regardless of whether ?range=custom is
    # explicitly set. This is the URL the user lands on after submitting the
    # custom date inputs.
    raw_from = request.args.get("from")
    raw_to = request.args.get("to")
    if raw_from and raw_to:
        try:
            d_from = date.fromisoformat(raw_from)
            d_to = date.fromisoformat(raw_to)
        except ValueError:
            return None, None, None
        if d_from > d_to:
            return None, None, None
        return d_from.isoformat(), d_to.isoformat(), "custom"

    return None, None, None


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
