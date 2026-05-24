---
description: Create a Single dummy user in the databse
allowed-tootls: Read,Bash(python3:*)
---
Read database/db.py to understand the user table schema and the get_db() helper.

Then write and run a Python Script using Bash that:
1. Genrate a realistic Ramdom user using your own knowledge of common indian names.
- Name: a realist Indian first + last name
- Email: derived form name with random 2-3 digit number suffix(e.g. anandmall04@gmail.com)
-Password: "password123" hashed with werkzeug's generate_passord_hash
- created_at: current datetime

2. Check if generated email already exist in the user table. If it does, regenerate until unique.
3. Insert the user into the databse using the same get_db() pattern found in db.py.
4. Print confirmation:
  - id
  - name
  - email
  