---
description: Create a spec file for next Expense Tracker Feature
argument-hent: "Step number and feature name e.g. 2 regristration"
allowed-tool: Read,Write,Glob
---

You are a Senior Developer planning a new feature for the Expense Tracker. Always Follow the rule in claude.md.

User input: $ARGUMENTS

## Step 1 - parse the arguments

From $ARGUMENTS extract:
1. 'Step_number' - Zero-padded to 2 digit : 2-> 02,11->11

2. 'Feature_title' - human readable title in Title Case
 - Example: "Registration" or "Login and LOgout"

3. 'Feature_slug' - file safe slug 
      - Lowercase, kebab-case
      - Only a-z, 0-9 and -
      - Maximum 40 charecters
      - Example: registraion, logina-logout
If you cannot infer from $ARGUMENTS ask the user to clarify before procceeding

## Step 2 - Reaserch the codebase
Read these file before writing the spec:
- CLAUDE.md - Roadmap convention schema
- app.py - Existing Route and structure
- database/db.py - Existing Schema and function
- All files in .claude/specs/ - avoid duplicating existing specs

Check claude.md to comfirm the requested step is not already mark complete. If it is warn the user and stop.

## Step 3 - Write the Spec
Generate the Spec document with this exact structure:

# Spec: <Feature_title>

## Overview
One Paragraph describing what this feature does and why it exist at this stage of Expense tracker Roadmap

## Depend On
Which Previous Step this feature Require to be completed

## Routes
Every New routes needed
- METHOD/path - description - access level (public/logged-in)
If No new routes: State "No new routes"

## Database Changes
Any new table ,columns or constraints needed.
Always verify against database/db.py before writing this.
If none: state "no Databse changes"

## Templates
- Create: list new templates with their path
- Modify: list existing templates and what changes

## Files to change
Every file that will be modified.

## Files to create
Every new file that will be created.

## New dependencies
Any new pip packages.
If none: state "No new dependencies".

## Rules for implementation
Specific constraints Claude must follow.
Always include:
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables - never hardcode hex values
- All templates extend base.html

## Definition of done
A specific testable checklist. Each item must be something that can be verified by running

## Step 4 - Save the spec
Save to: .claude/specs/
<step_number>-<feature_slug>.md

## Step 5 - Report to the user
Print a short summary in this exact format:

Spec file: .claude/specs/
<step_number>-<feature_slug>.md
Title: <feature_title>

Then tell the user:
"Review the spec at .claude/specs/
<step_number>-<feature_slug>.md
then enter Plan Mode with Shift+Tab twice to begin implementation."