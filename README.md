# 💸 Expense Tracker
### Flask Edition — GitLab + PythonAnywhere

> A multi-user expense tracker built with Python, Flask, and SQLite — hosted for free on PythonAnywhere.

---

## Overview

This is the original server-side version of the Expense Tracker. It runs a real Python/Flask web server with a persistent SQLite database, multi-user authentication via Werkzeug, and full CRUD for expenses and budgets.

The app is stored in a GitLab repository and deployed to [PythonAnywhere](https://www.pythonanywhere.com) — a free Python hosting platform. The WSGI configuration file (`pythonanywhere_wsgi.py`) is already included in the repo and just needs your username filled in.

---

## Features

| | |
|---|---|
| ✅ Multi-user login & signup | ✅ Monthly budget limits |
| ✅ Add & delete expenses | ✅ Over-budget alerts |
| ✅ 12 spending categories | ✅ Daily & category charts |
| ✅ Payment method tracking | ✅ 6-month trend chart |
| ✅ Monthly dashboard & stats | ✅ CSV export |
| ✅ Category spending bars | ✅ Mobile responsive UI |

---

## Repository Structure

| File | Purpose |
|---|---|
| `expense_tracker.py` | Main Flask app — all routes, DB layer, HTML templates |
| `pythonanywhere_wsgi.py` | WSGI config for PythonAnywhere (edit `USERNAME` before use) |
| `requirements.txt` | Python dependencies: `flask`, `werkzeug` |
| `.gitlab-ci.yml` | *(Optional)* CI pipeline for lint / tests |
| `expenses.db` | SQLite database — auto-created on first run, gitignored |

---

## Tech Stack

| Component | Detail |
|---|---|
| Language | Python 3.8+ |
| Framework | Flask |
| Auth | Werkzeug (bcrypt-based password hashing) |
| Database | SQLite via `sqlite3` (stdlib — no extra install) |
| Templating | Jinja2 via `render_template_string` |
| Hosting | PythonAnywhere (free tier) |
| Source | GitLab |

---

## Environment Variables

Set these in the WSGI file on PythonAnywhere (or in your shell for local dev):

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session secret — change to any random string |
| `DB_PATH` | Absolute path to the SQLite file, e.g. `/home/username/expense_tracker/expenses.db` |

> ⚠️ **Security:** Never commit `SECRET_KEY` or a production database to GitLab. Add `expenses.db` to `.gitignore`.

---

## Local Development Setup

1. **Clone the repo:**
   ```bash
   git clone https://gitlab.com/your-username/expense-tracker.git
   cd expense-tracker
   ```

2. **Install dependencies:**
   ```bash
   pip install flask werkzeug
   ```

3. **Run the app:**
   ```bash
   python expense_tracker.py
   ```

4. Open [http://localhost:5000](http://localhost:5000) in your browser.

> 💡 **Tip:** The app auto-creates the SQLite database (`expense_tracker.db`) in the current directory on first run — no setup needed.

---

## Deploying to PythonAnywhere

PythonAnywhere offers a **permanently free tier** that supports Flask apps with SQLite. No credit card required.

### Step 1 — Create a PythonAnywhere Account

1. Go to [pythonanywhere.com](https://www.pythonanywhere.com) and sign up for a free Beginner account.
2. Note your username — you'll need it in the WSGI config.

### Step 2 — Upload Your Code from GitLab

In the PythonAnywhere dashboard, open a **Bash console** and run:

```bash
git clone https://gitlab.com/your-username/expense-tracker.git
cd expense-tracker
pip install --user flask werkzeug
```

### Step 3 — Configure the Web App

1. In the PythonAnywhere dashboard, go to **Web tab → Add a new web app**.
2. Choose **Manual configuration** (not Flask) → select Python 3.10.
3. Click the **WSGI configuration file** link. Delete all existing content.
4. Paste the contents of `pythonanywhere_wsgi.py` from your repo.
5. Replace `your_username` with your actual PythonAnywhere username on the `USERNAME` line.
6. Change `SECRET_KEY` to a random string (anything long and unique).
7. Save the file, then click the green **Reload** button at the top of the Web tab.

### Step 4 — Visit Your Live App

Your app is now live at:

```
https://your-username.pythonanywhere.com
```

> ✅ The SQLite database is created automatically on the first request. Sign up for an account on the live site to get started.

---

## Updating the App

To push code changes from GitLab to PythonAnywhere, open a **Bash console** on PythonAnywhere and run:

```bash
cd ~/expense-tracker
git pull origin main
```

Then go to the **Web tab** → click **Reload** to apply the changes.

---

## Optional: GitLab CI/CD

Add a `.gitlab-ci.yml` file to your repo to automatically lint and test on every push:

```yaml
stages:
  - test

test:
  image: python:3.10
  stage: test
  script:
    - pip install flask werkzeug pytest
    - python -m py_compile expense_tracker.py
    - echo 'Syntax OK'
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| 500 error on load | Check the PythonAnywhere error log (Web tab → Log files → Error log). Usually a missing import or wrong path. |
| `ModuleNotFoundError: flask` | Run `pip install --user flask werkzeug` in a Bash console. |
| Database not saving data | Check `DB_PATH` in the WSGI file — it must be an absolute path inside your home directory. |
| Changes not appearing | Remember to click **Reload** in the Web tab after every `git pull`. |
| Forgot `SECRET_KEY` | Edit the WSGI file, set a new `SECRET_KEY`, and Reload. Existing sessions will be invalidated. |

---

## Known Limitations (Free Tier)

- PythonAnywhere free accounts can only serve **one web app**.
- The app is publicly accessible — anyone with the URL can sign up. Consider adding an invite-only mode for private use.
- SQLite is single-writer; fine for personal/small team use, not suited for high concurrency.
- PythonAnywhere free tier has a **CPU usage quota** per day — more than sufficient for personal use.

---

*Flask • SQLite • PythonAnywhere • GitLab • Free forever*
