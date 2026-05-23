import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

DATABASE = 'expense_tracker.db'


def get_db():
    """Get a database connection with foreign keys enabled and row factory."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Initialize database tables - safe to run multiple times."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Expenses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        conn.commit()


def seed_db():
    """Seed database with demo data - only runs if no users exist."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if users already exist
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] > 0:
            return  # Already seeded

        # Create demo user
        demo_password_hash = generate_password_hash('demo123')
        cursor.execute('''
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
        ''', ('Demo User', 'demo@spendly.com', demo_password_hash))

        user_id = cursor.lastrowid

        # Define expense categories (from spec)
        categories = ['Food', 'Transport', 'Bills', 'Health', 'Entertainment', 'Shopping', 'Other']

        # Generate 8 sample expenses across current month
        base_date = datetime.now().date()
        expenses_data = [
            # Spread across different days and categories
            (user_id, 12.50, 'Food', (base_date - timedelta(days=2)).isoformat(), 'Coffee and pastry'),
            (user_id, 45.00, 'Transport', (base_date - timedelta(days=5)).isoformat(), 'Gas refill'),
            (user_id, 89.99, 'Shopping', (base_date - timedelta(days=3)).isoformat(), 'New shirt'),
            (user_id, 120.00, 'Bills', (base_date - timedelta(days=10)).isoformat(), 'Electricity bill'),
            (user_id, 25.00, 'Health', (base_date - timedelta(days=7)).isoformat(), 'Pharmacy'),
            (user_id, 30.00, 'Entertainment', (base_date - timedelta(days=1)).isoformat(), 'Movie tickets'),
            (user_id, 15.75, 'Food', (base_date - timedelta(days=4)).isoformat(), 'Lunch'),
            (user_id, 65.00, 'Shopping', (base_date - timedelta(days=8)).isoformat(), 'Groceries'),
        ]

        cursor.executemany('''
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
        ''', expenses_data)

        conn.commit()
