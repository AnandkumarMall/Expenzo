# Database Layer Specification — Spendly

## 1. Overview

Replace the stub implementation in `database/db.py` with a fully working SQLite-based database layer.

This establishes the foundational data layer for the Spendly application.

All future features such as:
- Authentication
- User profiles
- Expense tracking
- Analytics

will depend on this implementation.

---

# 2. Dependencies

This task has no dependencies and should be implemented first.

---

# 3. Routes

No new routes are required.

Existing placeholder routes in `app.py` should remain unchanged.

---

# 4. Database Schema

## A. `users` Table

| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT |
| name | TEXT | NOT NULL |
| email | TEXT | UNIQUE, NOT NULL |
| password_hash | TEXT | NOT NULL |
| created_at | TEXT | DEFAULT datetime('now') |

---

## B. `expenses` Table

| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT |
| user_id | INTEGER | NOT NULL, FOREIGN KEY → users.id |
| amount | REAL | NOT NULL |
| category | TEXT | NOT NULL |
| date | TEXT | NOT NULL (YYYY-MM-DD format) |
| description | TEXT | Nullable |
| created_at | TEXT | DEFAULT datetime('now') |

---

# 5. Functions to Implement (`database/db.py`)

## A. `get_db()`

### Responsibilities
- Open a connection to:
  - `spendly.db`
  - OR `expense_tracker.db`
- Database should exist in the project root

### Requirements
- Set:
  ```python
  conn.row_factory = sqlite3.Row
  ```

- Enable foreign key support:
  ```sql
  PRAGMA foreign_keys = ON
  ```

- Return the SQLite connection object

---

## B. `init_db()`

### Responsibilities
- Create all required tables using:
  ```sql
  CREATE TABLE IF NOT EXISTS
  ```

### Requirements
- Safe to run multiple times
- Must initialize:
  - `users`
  - `expenses`

- Ensure proper:
  - constraints
  - foreign keys
  - defaults

---

## C. `seed_db()`

### Responsibilities
Populate the database with demo data.

### Rules
- Check whether the `users` table already contains data
- If data already exists:
  - return early
  - do NOT insert duplicates

### Insert Demo User
Use:
- Name: `Demo User`
- Email: `demo@spendly.com`
- Password: `demo123`

Password must be hashed using:

```python
from werkzeug.security import generate_password_hash
```

---

### Insert Sample Expenses

Insert:
- 8 sample expense records
- All linked to the demo user
- Spread across the current month
- Multiple categories represented
- At least one expense per category

---

# 6. Changes Required in `app.py`

## Imports

Import:
```python
from database.db import get_db, init_db, seed_db
```

---

## Startup Initialization

Call database setup during startup:

```python
with app.app_context():
    init_db()
    seed_db()
```

This ensures the database is ready before routes are used.

---

# 7. Files to Modify

| File | Changes |
|---|---|
| `database/db.py` | Implement database layer |
| `app.py` | Add DB imports and startup initialization |

---

# 8. Files to Create

No additional files required.

---

# 9. Dependencies

No new packages should be installed.

Use only:
- `sqlite3` (Python standard library)
- `werkzeug.security`

---

# 10. Fixed Expense Categories

Use exactly these category values:

- Food
- Transport
- Bills
- Health
- Entertainment
- Shopping
- Other

---

# 11. Implementation Rules

## Database Rules
- Do NOT use ORMs
- Do NOT use SQLAlchemy
- Use raw SQLite only

---

## Query Rules
- Use parameterized queries ONLY
- Never use string interpolation for SQL

Correct:
```python
cursor.execute(
    "SELECT * FROM users WHERE email = ?",
    (email,)
)
```

Incorrect:
```python
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
```

---

## Connection Rules
Every database connection must enable:

```sql
PRAGMA foreign_keys = ON
```

---

## Data Rules
- Store monetary values using:
  ```sql
  REAL
  ```

- Passwords must always be hashed

- Dates must use:
  ```text
  YYYY-MM-DD
  ```

---

## Seeding Rules
- `seed_db()` must be idempotent
- Running multiple times must NOT create duplicates

---

# 12. Expected Behavior

## `get_db()`
Should return:
- Working SQLite connection
- Dictionary-style row access
- Foreign key enforcement enabled

---

## `init_db()`
Should:
- Create tables safely
- Work on repeated runs
- Not overwrite existing data

---

## `seed_db()`
Should:
- Insert demo data only once
- Avoid duplicate records
- Create realistic sample data

---

## Database Constraints
The database must enforce:
- Unique emails
- Valid foreign keys
- Required fields

---

# 13. Error Handling Expectations

## Duplicate Email
Attempting to insert an existing email should fail with:
- SQLite UNIQUE constraint error

---

## Invalid Foreign Key
Attempting to insert an expense with an invalid `user_id` should fail with:
- Foreign key constraint error

---

## Invalid SQL
Broken or invalid queries should raise clear SQLite exceptions for debugging.

---

# 14. Definition of Done

- [ ] Database file created automatically on startup
- [ ] Both tables exist with correct schema
- [ ] Foreign key constraints work
- [ ] Demo user exists
- [ ] Password is hashed
- [ ] 8 sample expenses inserted
- [ ] No duplicate seed data on repeated runs
- [ ] App starts without errors
- [ ] All SQL uses parameterized queries
- [ ] Dates use consistent YYYY-MM-DD format