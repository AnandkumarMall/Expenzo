# Registration Feature Specification — Spendly

## 1. Overview

Implement the user registration functionality for Spendly. This feature allows new users to create an account by providing their name, email address, and password. Upon successful registration, users will shown succes message and then redirected to login page from where he be able to log in and access the expense tracking features.

This implementation completes the registration flow that was partially implemented with a GET route that only displays the form. The POST handler will process form submissions, validate input, create user accounts in the database, and handle appropriate error cases.

## 2. Dependencies

This feature depends on:
- Step 1: Database setup (must be complete) - provides the users table schema and database helper functions
- The registration feature requires the users table to exist with proper schema

## 3. Routes

- `GET /register` — Existing — displays registration form — public access
- `POST /register` — New — processes registration form submission — public access

## 4. Database Changes

No database changes required. The users table was already created in Step 1 (database setup) with the following schema:
- id INTEGER PRIMARY KEY AUTOINCREMENT
- name TEXT NOT NULL
- email TEXT UNIQUE NOT NULL
- password_hash TEXT NOT NULL
- created_at TEXT DEFAULT (datetime('now'))

## 5. Templates

**Create:** None (registration form template already exists)

**Modify:**
- `templates/register.html` — Add server-side error handling and success messaging (optional enhancement)

## 6. Files to Change

| File | Changes |
|------|---------|
| `app.py` | Add POST /register route handler for form processing |
| `templates/register.html` | (Optional) Enhance to display success/error messages from server |

## 7. Files to Create

No new files required.

## 8. New Dependencies

No new dependencies required. Will use:
- `flask.request` for form data access
- `werkzeug.security.generate_password_hash` (already imported)
- `database.db.get_db()` for database connections

## 9. Rules for Implementation

- **Database Rules:** Use parameterized queries only, never string interpolation in SQL
- **Password Security:** Always hash passwords using werkzeug.security.generate_password_hash
- **Input Validation:** Validate all form inputs (name, email, password) before processing
- **Error Handling:** Handle duplicate email addresses gracefully with user-friendly messages
- **HTTP Methods:** Separate GET (form display) and POST (form processing) handlers
- **Redirects:** After successful registration, redirect to login page
- **Flash Messages:** Use Flask's flashing mechanism for success/error messages (if implemented)
- **No Hardcoded URLs:** Use url_for() for all internal links

## 10. Implementation Details

### POST /register Route Handler

The route handler should:
1. Only accept POST requests
2. Extract form data: name, email, password
3. Validate inputs:
   - Name: not empty, reasonable length
   - Email: not empty, valid format, not already registered
   - Password: not empty, minimum length (6 characters)
4. If validation fails, re-render registration form with error messages
5. If email already exists, show error message
6. If validation passes:
   - Hash the password using generate_password_hash()
   - Insert new user into users table
   - Redirect to login page with success message

### Database Operations

Use parameterized queries for all database operations:
```python
# Check if email exists
cursor.execute("SELECT id FROM users WHERE email = ?", (email,))

# Insert new user
cursor.execute(
    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
    (name, email, hashed_password)
)
```

## 11. Definition of Done

- [ ] GET /register route continues to work (displays form)
- [ ] POST /register route properly handles form submissions
- [ ] Form validation works for all fields (name, email, password)
- [ ] Duplicate email detection works and shows appropriate error
- [ ] Passwords are properly hashed before storage
- [ ] New users are successfully inserted into the database
- [ ] Successful registration redirects to login page
- [ ] Error cases are handled gracefully with user feedback
- [ ] All SQL queries use parameterized statements (no f-string SQL)
- [ ] No hardcoded URLs in templates or route functions
- [ ] Template continues to extend base.html
- [ ] Application starts without errors
- [ ] Manual testing confirms:
  - Valid registration creates account and redirects
  - Duplicate email shows error
  - Missing fields show validation errors
  - Password is stored as hash (not plain text)
