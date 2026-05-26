---
# Spec: Login and Logout

## Overview
This feature allows existing users to authenticate using their email and password and securely end their session. Authentication is essential for protecting user data and is a prerequisite for the personalized expense tracking features in subsequent steps.

## Depends on
- 02-registration

## Routes
- `GET /login` — Render login form — public
- `POST /login` — Authenticate user and create session — public
- `GET /logout` — End user session and redirect — logged-in

## Database changes
No database changes.

## Templates
- **Modify:** `templates/login.html` — add the login form and error message display logic.

## Files to change
- `app.py` — update `/login` to handle POST requests and implement `/logout`.
- `database/db.py` — add helper function to verify user credentials.
- `templates/login.html` — implement the form.

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords verified using `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic must reside in `database/db.py`

## Definition of done
- [ ] User can successfully log in with valid credentials and is redirected to the landing page.
- [ ] User is shown a clear error message when providing invalid credentials.
- [ ] User can successfully log out, clearing the session and redirecting to the login page.
- [ ] A logged-out user cannot access restricted routes (once implemented in future steps).
- [ ] The application does not crash when attempting to log out without an active session.
---
