from flask import Flask, render_template, request, redirect, url_for, session, abort
from database.db import (
    get_db, init_db, seed_db, get_user_by_email,
    get_user_by_id, get_expenses_for_user, count_expenses_for_user,
    get_total_spent, get_top_category, get_category_breakdown,
    add_expense as add_expense_to_db,
    get_expense_by_id, update_expense, delete_expense as delete_expense_db,
    EXPENSE_CATEGORIES,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import math

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
        {"id": r["id"], "date": r["date"], "desc": r["description"] or "", "cat": r["category"], "amt": r["amount"]}
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


def _empty_form_values(date_str):
    """Return the four-field dict used to render the add-expense form's GET
    branch and the round-trip error branch. Centralised so the two call sites
    cannot drift if a fifth field is ever added.
    """
    return {"amount": "", "category": "", "date": date_str, "description": ""}


def _validate_amount(raw):
    """Validate a raw form string for the amount field. Returns the parsed
    value (rounded to 2dp) on success, or None on any validation failure.
    Callers must inspect the tuple's second element for the user-facing error
    message and the third for the field name used to drive the highlight.

    Pulled out of the route so the four-step validation (required, numeric,
    finite, positive) reads as a flat list and so the same pattern can be
    reused by Step 8 (edit) without copy-paste.
    """
    if not raw:
        return None, "Amount is required.", "amount"
    try:
        amount = float(raw)
    except ValueError:
        return None, "Amount must be a number.", "amount"
    if not math.isfinite(amount):
        return None, "Amount must be a real number.", "amount"
    if amount <= 0:
        return None, "Amount must be greater than zero.", "amount"
    return round(amount, 2), None, None


def _validate_expense_form(amount, amount_raw, category, date_raw, desc_raw):
    """Validate the remaining three expense fields (category, date,
    description) AND build the round-trip dict the template needs to
    rehydrate the form on a validation error.

    Returns (values, error, field_error):

    - `values` is a round-trip dict the template uses to rehydrate the
      form. `amount` carries the **raw** submitted string (not the
      parsed float) so an invalid entry like "abc" round-trips back to
      the input the user actually typed. The other three keys are the
      raw .strip()ed strings. `description_clean` (None when blank) is
      the value to persist on the success path.
    - `error` is the user-facing message, or None on success.
    - `field_error` is the field name ("category" / "date" / "description")
      used to drive the .field-error highlight, or None on success.

    The dict is built unconditionally — even when this helper returns
    a successful (no error) result, the caller still has the round-trip
    dict for the success-path persistence. When `_validate_amount`
    fails first, the caller overrides `error` / `field_error` to surface
    the amount error while keeping the same round-trip `values` shape.

    Shared by /expenses/add and /expenses/<id>/edit so the rules cannot
    drift between the two routes. The amount field is intentionally
    NOT validated here — that is _validate_amount's job, called first
    by the route.
    """
    values = {
        "amount": amount_raw,
        "category": category,
        "date": date_raw,
        "description": desc_raw,
        "description_clean": desc_raw if desc_raw else None,
    }

    # category: empty is "required", any other non-canonical value is
    # "validity". Server-side guard catches anything the <select>
    # constraint would normally block (curl, DevTools tampering, etc.).
    if not category:
        return values, "Category is required.", "category"
    if category not in EXPENSE_CATEGORIES:
        return values, "Please choose a valid category.", "category"

    # date: required, ISO YYYY-MM-DD, not in the future. Empty check
    # comes first because strptime('') raises ValueError.
    if not date_raw:
        return values, "Date is required.", "date"
    try:
        parsed_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
    except ValueError:
        return values, "Date must be in YYYY-MM-DD format.", "date"
    if parsed_date > _today():
        return values, "Date cannot be in the future.", "date"

    # description: optional, capped at 200 chars on the server. The
    # <textarea maxlength> is client-side only; a curl request bypasses it.
    if desc_raw and len(desc_raw) > 200:
        return values, "Description must be 200 characters or fewer.", "description"

    return values, None, None


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


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    # Auth gate — must run on both GET and POST, before reading request.form,
    # so logged-out users never see the form and can never submit inserts.
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "POST":
        # Parse form. Empty string is the sentinel for "missing" everywhere
        # below; .strip() matches the convention used in /register.
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        desc_raw = request.form.get("description", "").strip()

        # amount: required, finite, > 0. _validate_amount returns the parsed
        # float (or None) plus the user-facing error and the field name.
        amount, amount_err, amount_field = _validate_amount(amount_raw)

        # category / date / description: validated together by the shared
        # helper, which also builds the round-trip `values` dict. The dict
        # is built unconditionally — if the amount failed first we still
        # have a valid round-trip shape for the form, and we override the
        # helper's error/field_error with the amount's.
        values, error, field_error = _validate_expense_form(
            amount, amount_raw, category, date_raw, desc_raw
        )
        if amount_err is not None:
            error, field_error = amount_err, amount_field

        if error is not None:
            return render_template(
                "add_expense.html",
                values=values,
                categories=EXPENSE_CATEGORIES,
                error=error,
                field_error=field_error,
                submit_label="Add expense",
            )

        # Success path — insert, then redirect to the dashboard.
        add_expense_to_db(
            session["user_id"],
            amount,
            category,
            date_raw,
            values["description_clean"],
        )
        return redirect(url_for("profile"))

    # GET — render the empty form. Date is pre-filled with today so the
    # common case is "type an amount, hit save".
    return render_template(
        "add_expense.html",
        values=_empty_form_values(_today().isoformat()),
        categories=EXPENSE_CATEGORIES,
        error=None,
        field_error=None,
        submit_label="Add expense",
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    # Auth gate — must run on both GET and POST, before reading request.form
    # or the row, so logged-out users never see the form and can never submit
    # an update.
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Fetch the row, scoped to the logged-in user. 404 for both
    # "does not exist" and "owned by another user" so the route does not
    # leak the existence of another user's row. The check happens before
    # any form read on both methods.
    expense = get_expense_by_id(user_id, id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        # Parse form. Empty string is the sentinel for "missing" everywhere
        # below; .strip() matches the convention used in /register and /add.
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        desc_raw = request.form.get("description", "").strip()

        # amount: required, finite, > 0. _validate_amount returns the parsed
        # float (or None) plus the user-facing error and the field name.
        amount, amount_err, amount_field = _validate_amount(amount_raw)

        # category / date / description: validated together by the shared
        # helper, which also builds the round-trip `values` dict. The dict
        # is built unconditionally — if the amount failed first we still
        # have a valid round-trip shape for the form, and we override the
        # helper's error/field_error with the amount's.
        values, error, field_error = _validate_expense_form(
            amount, amount_raw, category, date_raw, desc_raw
        )
        if amount_err is not None:
            error, field_error = amount_err, amount_field

        if error is not None:
            return render_template(
                "edit_expense.html",
                expense=expense,
                values=values,
                categories=EXPENSE_CATEGORIES,
                error=error,
                field_error=field_error,
                submit_label="Save changes",
            )

        # Success path — update the row in place. The WHERE clause includes
        # user_id, so a user can never mutate another user's row even if
        # they POST to the right id. created_at is intentionally not in the
        # SET list — that column records the original insert time and is
        # immutable from the application's perspective.
        update_expense(
            user_id,
            id,
            amount,
            category,
            date_raw,
            values["description_clean"],
        )
        return redirect(url_for("profile"))

    # GET — render the form pre-filled with the row's current values.
    # Amount is rendered as a plain decimal so the field starts out
    # looking like an editable number; description falls back to ""
    # when the stored value is NULL.
    return render_template(
        "edit_expense.html",
        expense=expense,
        values={
            "amount": f"{expense['amount']:.2f}",
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        },
        categories=EXPENSE_CATEGORIES,
        error=None,
        field_error=None,
        submit_label="Save changes",
    )


@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])
def delete_expense(id):
    # Auth gate — must run on both GET and POST, before reading the row,
    # so logged-out users never see the confirmation page and can never
    # submit a delete.
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Fetch the row, scoped to the logged-in user. 404 for both
    # "does not exist" and "owned by another user" so the route does
    # not leak the existence of another user's row.
    expense = get_expense_by_id(user_id, id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        # DELETE is guarded by user_id inside the helper, so a user can
        # never delete another user's row even if they POST to the right
        # id. The pre-flight get_expense_by_id above makes a 0-rowcount
        # result unreachable in practice, but we still commit and redirect.
        delete_expense_db(user_id, id)
        return redirect(url_for("profile"))

    # GET — render the confirmation page with the row's fields displayed
    # for review. The `values` dict matches the shape edit_expense.html
    # reads, so the template iterates one source of display data.
    return render_template(
        "delete_expense.html",
        expense=expense,
        values={
            "date": expense["date"],
            "category": expense["category"],
            "amount": format_inr(expense["amount"]),
            "description": expense["description"] or "—",
        },
    )


# Initialize database on startup
with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
