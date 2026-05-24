---
description: Seed realistic dummy expenses for a sepecific user
argument-hint: "<user-id> <count> <months>"
allowed-tools: Read, Bash(python3:*)
---

read database/db.py to understand the expense table
Schema, the db connection pattern and the database
file name.

User input: $ARGUMENTS

## Step 1 - Parse arguments

Extract from $ARGUMENTS:
- user_id-integer
-count- integer,number of expense to create
-months- integer,how many past months to spread across

If any arguments is missing or not a valid integer, stop and say:
"Usage: /seed-expense <user_id> <count> <months>
Example: /seed-expense 1 50 6"

## Step 2 - Verify User exists
Before generating anything, confirm the user exist in usertable. If not,Stop and Say:"No user found with id <user_id>."

## Step 3 - Generate and insert Expense
Write a python script that :
1. Spreads Expense Randomly across the past <months> months
2. Use this categories with realistic indian discription and amount(₹):
-Food 50-800
- Transport: 20-500
-Bills:200-3000
-Health:100-2000
-Entertainment: 100-1500
-Shopping: 200-5000
-Other:50-1000
3. distribute categories Roughly Proportionally
  (Food most common ,Health and Entertainment Least)

4. Use db connection pattern from db.py
 donot hardcode databse filename
5. Use parametarise queries only - no string Formetting in SQL
6. Insert all expense in Single transaction roll back everything if insert fail.

## Step 4 - Confirm

- Print- Howmany expense were inserted
- The Date range they Span
- A Smaple of 5 record