"""
╔══════════════════════════════════════════════════════════════════╗
║      EXPENSE TRACKER — Multi-User, PostgreSQL, Flask             ║
║                                                                  ║
║  LOCAL INSTALL:                                                  ║
║    pip install flask werkzeug psycopg2-binary gunicorn           ║
║                                                                  ║
║  LOCAL RUN (uses SQLite fallback if no DATABASE_URL set):        ║
║    python expense_tracker.py                                     ║
║                                                                  ║
║  RAILWAY: set DATABASE_URL env var (auto-set by Railway Postgres)║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, csv, io, datetime, socket
from pathlib import Path
from functools import wraps
from flask import (Flask, render_template_string, request,
                   redirect, url_for, session, make_response)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "expense-secret-2025")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

CATEGORIES = [
    "🍔 Food & Dining", "🚗 Transport", "🏠 Housing & Rent",
    "💡 Utilities", "🛍️ Shopping", "🎬 Entertainment",
    "💊 Health & Medical", "📚 Education", "✈️ Travel",
    "💼 Business", "🎁 Gifts", "📦 Other",
]
CAT_COLORS = [
    "#7c5cfc","#00d4aa","#ffd32a","#ff6b35","#ff4757",
    "#0066ff","#00c9ff","#a55eea","#26de81","#fd9644",
    "#45aaf2","#fc5c65"
]

# ══════════════════════════════════════════════════════════════
#  DATABASE LAYER  (PostgreSQL on Railway, SQLite locally)
# ══════════════════════════════════════════════════════════════
def get_conn():
    if DATABASE_URL:
        import psycopg2
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(url)
        conn.autocommit = False
        return conn, "pg"
    else:
        import sqlite3
        db_path = Path("expense_tracker.db")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def init_db():
    conn, kind = get_conn()
    cur = conn.cursor()
    if kind == "pg":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username   TEXT PRIMARY KEY,
                password   TEXT NOT NULL,
                joined     TEXT NOT NULL
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                amount      REAL NOT NULL,
                date        TEXT NOT NULL,
                description TEXT NOT NULL,
                category    TEXT NOT NULL,
                payment     TEXT,
                note        TEXT
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                username TEXT NOT NULL,
                category TEXT NOT NULL,
                amount   REAL NOT NULL,
                PRIMARY KEY (username, category)
            )""")
    else:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                joined   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id          TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                amount      REAL NOT NULL,
                date        TEXT NOT NULL,
                description TEXT NOT NULL,
                category    TEXT NOT NULL,
                payment     TEXT,
                note        TEXT
            );
            CREATE TABLE IF NOT EXISTS budgets (
                username TEXT NOT NULL,
                category TEXT NOT NULL,
                amount   REAL NOT NULL,
                PRIMARY KEY (username, category)
            );
        """)
    conn.commit()
    conn.close()

# ── User helpers ──────────────────────────────────────────────
def user_exists(username):
    conn, kind = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username=%s" if kind=="pg"
                else "SELECT 1 FROM users WHERE username=?", (username,))
    r = cur.fetchone(); conn.close(); return r is not None

def create_user(username, password):
    conn, kind = get_conn()
    cur = conn.cursor()
    ph = generate_password_hash(password)
    ph_today = datetime.date.today().strftime("%Y-%m-%d")
    cur.execute("INSERT INTO users VALUES (%s,%s,%s)" if kind=="pg"
                else "INSERT INTO users VALUES (?,?,?)",
                (username, ph, ph_today))
    conn.commit(); conn.close()

def verify_user(username, password):
    conn, kind = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=%s" if kind=="pg"
                else "SELECT password FROM users WHERE username=?", (username,))
    r = conn.cursor() if False else cur.fetchone()
    conn.close()
    if not r: return False
    return check_password_hash(r[0] if kind=="pg" else r["password"], password)

# ── Expense helpers ───────────────────────────────────────────
def add_expense(username, exp):
    conn, kind = get_conn()
    cur = conn.cursor()
    q = ("INSERT INTO expenses VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
         if kind=="pg" else
         "INSERT INTO expenses VALUES (?,?,?,?,?,?,?,?)")
    cur.execute(q, (exp["id"], username, exp["amount"], exp["date"],
                    exp["description"], exp["category"],
                    exp.get("payment",""), exp.get("note","")))
    conn.commit(); conn.close()

def get_expenses(username, month=None, category=None):
    conn, kind = get_conn()
    cur = conn.cursor()
    ph = "%s" if kind=="pg" else "?"
    q  = f"SELECT * FROM expenses WHERE username={ph}"
    params = [username]
    if month:
        q += f" AND date LIKE {ph}"; params.append(month+"%")
    if category:
        q += f" AND category={ph}"; params.append(category)
    q += " ORDER BY date DESC"
    cur.execute(q, params)
    rows = cur.fetchall(); conn.close()
    return [dict(r) for r in rows]

def delete_expense(username, eid):
    conn, kind = get_conn()
    cur = conn.cursor()
    ph = "%s" if kind=="pg" else "?"
    cur.execute(f"DELETE FROM expenses WHERE id={ph} AND username={ph}",
                (eid, username))
    conn.commit(); conn.close()

# ── Budget helpers ────────────────────────────────────────────
def get_budgets(username):
    conn, kind = get_conn()
    cur = conn.cursor()
    ph = "%s" if kind=="pg" else "?"
    cur.execute(f"SELECT category, amount FROM budgets WHERE username={ph}",
                (username,))
    rows = cur.fetchall(); conn.close()
    return {r[0]: r[1] for r in rows}

def set_budget(username, category, amount):
    conn, kind = get_conn()
    cur = conn.cursor()
    ph = "%s" if kind=="pg" else "?"
    if kind == "pg":
        cur.execute("""INSERT INTO budgets VALUES (%s,%s,%s)
                       ON CONFLICT (username,category)
                       DO UPDATE SET amount=EXCLUDED.amount""",
                    (username, category, amount))
    else:
        cur.execute("INSERT OR REPLACE INTO budgets VALUES (?,?,?)",
                    (username, category, amount))
    conn.commit(); conn.close()

def delete_budget_db(username, category):
    conn, kind = get_conn()
    cur = conn.cursor()
    ph = "%s" if kind=="pg" else "?"
    cur.execute(f"DELETE FROM budgets WHERE username={ph} AND category={ph}",
                (username, category))
    conn.commit(); conn.close()

# ── Utility ───────────────────────────────────────────────────
def month_summary(expenses, month_key):
    total, by_cat = 0, {}
    for e in expenses:
        if str(e["date"])[:7] == month_key:
            total += e["amount"]
            by_cat[e["category"]] = by_cat.get(e["category"],0) + e["amount"]
    return total, by_cat

def get_nav_months(mk):
    y,m = int(mk[:4]), int(mk[5:])
    pm = m-1 or 12; py = y if m>1 else y-1
    nm = (m%12)+1;  ny = y if m<12 else y+1
    return f"{py}-{pm:02d}", f"{ny}-{nm:02d}"

def login_required(f):
    @wraps(f)
    def dec(*a,**kw):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*a,**kw)
    return dec

def render(tmpl, **kw):
    kw.setdefault("session_user", session.get("username"))
    kw.setdefault("flash", None)
    kw.setdefault("flash_type", None)
    kw.setdefault("colors", CAT_COLORS)
    return render_template_string(tmpl, **kw)

# ══════════════════════════════════════════════════════════════
#  HTML TEMPLATES
# ══════════════════════════════════════════════════════════════
BASE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>💸 Expense Tracker</title>
<style>
:root{--bg:#0a0a0f;--panel:#111118;--card:#16161e;--card2:#1c1c26;
  --border:#2a2a3a;--accent:#7c5cfc;--green:#00d4aa;--red:#ff4757;
  --yellow:#ffd32a;--orange:#ff6b35;--text:#e8e8f0;--muted:#6b6b80;--r:12px;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);
  font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;}
a{color:inherit;text-decoration:none;}
nav{background:var(--panel);border-bottom:1px solid var(--border);
  padding:0 16px;display:flex;align-items:center;justify-content:space-between;
  height:54px;position:sticky;top:0;z-index:100;gap:8px;flex-wrap:wrap;}
.nav-brand{font-size:1.05rem;font-weight:700;color:var(--accent);}
.nav-links{display:flex;gap:2px;flex-wrap:wrap;}
.nav-links a{color:var(--muted);padding:6px 10px;border-radius:8px;
  font-size:.83rem;font-weight:500;transition:all .2s;white-space:nowrap;}
.nav-links a:hover,.nav-links a.active{background:var(--card2);color:var(--text);}
.nav-user{display:flex;align-items:center;gap:8px;font-size:.83rem;}
.nav-user span{color:var(--green);font-weight:600;}
.nav-user a{background:var(--card2);color:var(--muted);padding:5px 12px;
  border-radius:8px;border:1px solid var(--border);font-size:.8rem;transition:all .2s;}
.nav-user a:hover{border-color:var(--red);color:var(--red);}
.container{max-width:1080px;margin:0 auto;padding:20px 14px;}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;}
@media(max-width:680px){
  .grid-2,.grid-4{grid-template-columns:1fr;}
  nav{height:auto;padding:10px 14px;}
  .nav-links{justify-content:center;}}
.card{background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:18px;}
.card-title{font-size:.72rem;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;}
.stat-val{font-size:1.9rem;font-weight:700;}
.stat-sub{font-size:.78rem;color:var(--muted);margin-top:3px;}
.form-group{display:flex;flex-direction:column;gap:5px;margin-bottom:12px;}
.form-group label{font-size:.8rem;color:var(--muted);font-weight:500;}
input,select{background:var(--card2);border:1px solid var(--border);
  color:var(--text);padding:10px 13px;border-radius:8px;font-size:.93rem;
  width:100%;outline:none;transition:border-color .2s;font-family:inherit;}
input:focus,select:focus{border-color:var(--accent);}
select option{background:var(--card2);}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
@media(max-width:500px){.form-grid{grid-template-columns:1fr;}}
.btn{display:inline-flex;align-items:center;gap:5px;padding:10px 18px;
  border-radius:8px;font-size:.88rem;font-weight:600;border:none;cursor:pointer;
  text-decoration:none;transition:all .2s;}
.btn-primary{background:var(--accent);color:#fff;}
.btn-primary:hover{background:#6a4de8;}
.btn-green{background:var(--green);color:#000;}
.btn-green:hover{background:#00b894;}
.btn-red{background:var(--red);color:#fff;}
.btn-red:hover{background:#e0333f;}
.btn-ghost{background:var(--card2);color:var(--text);border:1px solid var(--border);}
.btn-ghost:hover{border-color:var(--accent);color:var(--accent);}
.btn-sm{padding:6px 11px;font-size:.78rem;}
.btn-full{width:100%;justify-content:center;}
.table-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:.88rem;}
th{background:var(--card2);color:var(--muted);font-size:.72rem;
  text-transform:uppercase;letter-spacing:.8px;padding:9px 13px;text-align:left;}
td{padding:11px 13px;border-bottom:1px solid var(--border);}
tr:last-child td{border-bottom:none;}
tr:hover td{background:var(--card2);}
.prog-wrap{background:var(--card2);border-radius:6px;height:7px;overflow:hidden;margin:5px 0;}
.prog-bar{height:100%;border-radius:6px;transition:width .4s;}
.bar-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.bar-label{width:130px;font-size:.8rem;color:var(--muted);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex-shrink:0;}
.bar-track{flex:1;background:var(--card2);border-radius:5px;height:20px;overflow:hidden;}
.bar-fill{height:100%;border-radius:5px;display:flex;align-items:center;
  padding-left:7px;font-size:.72rem;font-weight:600;color:#000;
  min-width:28px;transition:width .5s;}
.bar-amt{font-size:.8rem;color:var(--text);width:72px;text-align:right;flex-shrink:0;}
.donut-wrap{display:flex;align-items:center;gap:18px;flex-wrap:wrap;}
.donut{position:relative;width:120px;height:120px;flex-shrink:0;}
.donut svg{transform:rotate(-90deg);}
.donut-center{position:absolute;top:50%;left:50%;
  transform:translate(-50%,-50%);text-align:center;}
.donut-center .big{font-size:1.1rem;font-weight:700;}
.donut-center .sm{font-size:.68rem;color:var(--muted);}
.legend{display:flex;flex-direction:column;gap:5px;}
.legend-item{display:flex;align-items:center;gap:7px;font-size:.8rem;}
.legend-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;}
.page-title{font-size:1.4rem;font-weight:700;margin-bottom:3px;}
.page-sub{color:var(--muted);font-size:.87rem;margin-bottom:16px;}
.section-title{font-size:.95rem;font-weight:600;margin-bottom:12px;}
.flex-between{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;}
.flex{display:flex;align-items:center;}
.gap8{gap:8px;}
.mt8{margin-top:8px;}.mt12{margin-top:12px;}.mt16{margin-top:16px;}
.empty{text-align:center;padding:36px;color:var(--muted);font-size:.88rem;}
.green{color:var(--green);}.red{color:var(--red);}
.yellow{color:var(--yellow);}.accent{color:var(--accent);}
.flash{padding:11px 15px;border-radius:8px;margin-bottom:14px;font-size:.88rem;font-weight:500;}
.flash-ok{background:#00d4aa18;color:var(--green);border:1px solid #00d4aa35;}
.flash-err{background:#ff475718;color:var(--red);border:1px solid #ff475735;}
.auth-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}
.auth-box{background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:32px 28px;width:100%;max-width:400px;}
.auth-title{font-size:1.5rem;font-weight:700;color:var(--accent);text-align:center;margin-bottom:4px;}
.auth-sub{text-align:center;color:var(--muted);font-size:.85rem;margin-bottom:24px;}
.auth-switch{text-align:center;margin-top:16px;font-size:.85rem;color:var(--muted);}
.auth-switch a{color:var(--accent);font-weight:600;}
</style>
</head>
<body>
{% if session_user %}
<nav>
  <span class="nav-brand">💸 Expense Tracker</span>
  <div class="nav-links">
    <a href="/"         class="{{ 'active' if page=='dashboard' }}">📊 Dashboard</a>
    <a href="/expenses" class="{{ 'active' if page=='expenses'  }}">📋 Expenses</a>
    <a href="/add"      class="{{ 'active' if page=='add'       }}">➕ Add</a>
    <a href="/budgets"  class="{{ 'active' if page=='budgets'   }}">🎯 Budgets</a>
    <a href="/charts"   class="{{ 'active' if page=='charts'    }}">📈 Charts</a>
    <a href="/export"   class="btn btn-ghost btn-sm">⬇ CSV</a>
  </div>
  <div class="nav-user">
    <span>👤 {{ session_user }}</span>
    <a href="/logout">Logout</a>
  </div>
</nav>
{% endif %}
<div class="{{ 'container' if session_user else '' }}">
{% if flash %}
<div class="flash {{ 'flash-ok' if flash_type=='ok' else 'flash-err' }}">{{ flash }}</div>
{% endif %}
{% block content %}{% endblock %}
</div></body></html>"""

AUTH_LOGIN = BASE.replace("{% block content %}{% endblock %}", """
<div class="auth-wrap"><div class="auth-box">
  <div class="auth-title">💸 Expense Tracker</div>
  <div class="auth-sub">Sign in to your account</div>
  <form method="POST">
    <div class="form-group"><label>Username</label>
      <input name="username" placeholder="Enter username" required autofocus></div>
    <div class="form-group"><label>Password</label>
      <input name="password" type="password" placeholder="Enter password" required></div>
    <button class="btn btn-primary btn-full" style="margin-top:8px">🔑 Sign In</button>
  </form>
  <div class="auth-switch">No account? <a href="/signup">Sign up →</a></div>
</div></div>""")

AUTH_SIGNUP = BASE.replace("{% block content %}{% endblock %}", """
<div class="auth-wrap"><div class="auth-box">
  <div class="auth-title">💸 Create Account</div>
  <div class="auth-sub">Start tracking your expenses</div>
  <form method="POST">
    <div class="form-group"><label>Username</label>
      <input name="username" placeholder="Choose a username (min 3 chars)" required autofocus></div>
    <div class="form-group"><label>Password</label>
      <input name="password" type="password" placeholder="Min 4 characters" required></div>
    <div class="form-group"><label>Confirm Password</label>
      <input name="confirm" type="password" placeholder="Repeat password" required></div>
    <button class="btn btn-green btn-full" style="margin-top:8px">✅ Create Account</button>
  </form>
  <div class="auth-switch">Have an account? <a href="/login">Sign in →</a></div>
</div></div>""")

DASHBOARD = BASE.replace("{% block content %}{% endblock %}", """
<div class="flex-between">
  <div>
    <div class="page-title">Dashboard</div>
    <div class="page-sub">{{ month_label }} • {{ session_user }}'s expenses</div>
  </div>
  <div class="flex gap8">
    <a href="?month={{ prev_month }}" class="btn btn-ghost btn-sm">‹ Prev</a>
    <a href="?month={{ next_month }}" class="btn btn-ghost btn-sm">Next ›</a>
  </div>
</div>
<div class="grid-4 mt8">
  <div class="card"><div class="card-title">Total Spent</div>
    <div class="stat-val red">₹{{ "%.2f"|format(total) }}</div>
    <div class="stat-sub">this month</div></div>
  <div class="card"><div class="card-title">Transactions</div>
    <div class="stat-val accent">{{ count }}</div>
    <div class="stat-sub">expenses logged</div></div>
  <div class="card"><div class="card-title">Avg / Day</div>
    <div class="stat-val yellow">₹{{ "%.0f"|format(avg_day) }}</div>
    <div class="stat-sub">daily average</div></div>
  <div class="card"><div class="card-title">Top Category</div>
    <div class="stat-val" style="font-size:1.1rem">{{ top_cat or '—' }}</div>
    <div class="stat-sub">{{ "₹%.2f"|format(top_amt) if top_cat else 'no data' }}</div></div>
</div>
<div class="grid-2 mt16">
  <div class="card">
    <div class="flex-between"><div class="section-title">Recent Expenses</div>
      <a href="/expenses" class="btn btn-ghost btn-sm">View All</a></div>
    {% if recent %}
    <div class="table-wrap"><table>
      <thead><tr><th>Date</th><th>Description</th><th>Amount</th></tr></thead>
      <tbody>{% for e in recent %}<tr>
        <td style="color:var(--muted);font-size:.8rem">{{ e.date }}</td>
        <td><div>{{ e.description }}</div>
          <div style="font-size:.75rem;color:var(--muted)">{{ e.category }}</div></td>
        <td class="red" style="font-weight:700">₹{{ "%.2f"|format(e.amount) }}</td>
      </tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<div class="empty">No expenses yet.<br>
      <a href="/add" class="accent">Add one →</a></div>{% endif %}
  </div>
  <div class="card">
    <div class="flex-between"><div class="section-title">Budget Status</div>
      <a href="/budgets" class="btn btn-ghost btn-sm">Edit</a></div>
    {% if budgets %}
      {% for cat,limit in budgets.items() %}
        {% set spent=by_cat.get(cat,0) %}
        {% set pct=[[spent/limit*100 if limit>0 else 0,0]|max,100]|min %}
        {% set col='#ff4757' if pct>90 else ('#ffd32a' if pct>70 else '#00d4aa') %}
        <div class="flex-between mt8" style="font-size:.83rem">
          <span>{{ cat }}</span>
          <span style="color:var(--muted)">₹{{ "%.0f"|format(spent) }} / ₹{{ "%.0f"|format(limit) }}</span>
        </div>
        <div class="prog-wrap">
          <div class="prog-bar" style="width:{{ pct }}%;background:{{ col }}"></div>
        </div>
      {% endfor %}
    {% else %}<div class="empty">No budgets.<br>
      <a href="/budgets" class="accent">Set budgets →</a></div>{% endif %}
  </div>
</div>
<div class="card mt16"><div class="section-title">Spending by Category</div>
  {% if by_cat %}
    {% set max_val=by_cat.values()|max %}
    {% for cat,amt in by_cat|dictsort(by='value',reverse=true) %}
      {% set pct=(amt/max_val*100)|int if max_val>0 else 0 %}
      {% set ci=loop.index0 % colors|length %}
      <div class="bar-row">
        <div class="bar-label">{{ cat }}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:{{ pct }}%;background:{{ colors[ci] }}">{{ pct }}%</div>
        </div>
        <div class="bar-amt">₹{{ "%.0f"|format(amt) }}</div>
      </div>
    {% endfor %}
  {% else %}<div class="empty">No spending data this month.</div>{% endif %}
</div>""")

ADD_PAGE = BASE.replace("{% block content %}{% endblock %}", """
<div class="page-title">Add Expense</div>
<div class="page-sub">Log a new transaction</div>
<div class="card" style="max-width:580px">
  <form method="POST">
    <div class="form-grid">
      <div class="form-group"><label>Amount (₹) *</label>
        <input type="number" name="amount" placeholder="0.00" step="0.01" min="0.01" required></div>
      <div class="form-group"><label>Date *</label>
        <input type="date" name="date" value="{{ today }}" required></div>
      <div class="form-group" style="grid-column:1/-1"><label>Description *</label>
        <input type="text" name="description" placeholder="e.g. Lunch at cafe" required></div>
      <div class="form-group"><label>Category *</label>
        <select name="category" required>
          {% for cat in categories %}<option>{{ cat }}</option>{% endfor %}
        </select></div>
      <div class="form-group"><label>Payment Method</label>
        <select name="payment">
          <option>💵 Cash</option><option>💳 Card</option>
          <option>📱 UPI</option><option>🏦 Bank Transfer</option>
          <option>📲 Wallet</option>
        </select></div>
      <div class="form-group" style="grid-column:1/-1"><label>Note (optional)</label>
        <input type="text" name="note" placeholder="Optional note..."></div>
    </div>
    <button type="submit" class="btn btn-primary btn-full">💾 Save Expense</button>
  </form>
</div>""")

EXPENSES_PAGE = BASE.replace("{% block content %}{% endblock %}", """
<div class="flex-between">
  <div><div class="page-title">All Expenses</div>
    <div class="page-sub">{{ total_count }} transactions • Total: ₹{{ "%.2f"|format(grand_total) }}</div></div>
  <div class="flex gap8">
    <a href="/add" class="btn btn-primary btn-sm">➕ Add</a>
    <a href="/export" class="btn btn-ghost btn-sm">⬇ CSV</a>
  </div>
</div>
<div class="card mt8" style="padding:12px">
  <form method="GET" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
    <div class="form-group" style="min-width:130px;margin:0"><label>Month</label>
      <input type="month" name="month" value="{{ filter_month }}"></div>
    <div class="form-group" style="min-width:170px;margin:0"><label>Category</label>
      <select name="category">
        <option value="">All Categories</option>
        {% for cat in categories %}
        <option value="{{ cat }}" {{ 'selected' if filter_cat==cat }}>{{ cat }}</option>
        {% endfor %}
      </select></div>
    <button type="submit" class="btn btn-ghost btn-sm">🔍 Filter</button>
    <a href="/expenses" class="btn btn-ghost btn-sm">✕ Clear</a>
  </form>
</div>
<div class="card mt12">
  {% if expenses %}
  <div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Description</th><th>Category</th>
      <th>Payment</th><th>Amount</th><th></th></tr></thead>
    <tbody>{% for e in expenses %}<tr>
      <td style="color:var(--muted);font-size:.8rem;white-space:nowrap">{{ e.date }}</td>
      <td><div style="font-weight:500">{{ e.description }}</div>
        {% if e.note %}<div style="font-size:.75rem;color:var(--muted)">{{ e.note }}</div>{% endif %}</td>
      <td style="font-size:.8rem">{{ e.category }}</td>
      <td style="font-size:.8rem;color:var(--muted)">{{ e.payment }}</td>
      <td style="font-weight:700;color:var(--red);white-space:nowrap">₹{{ "%.2f"|format(e.amount) }}</td>
      <td><a href="/delete/{{ e.id }}"
             onclick="return confirm('Delete this expense?')"
             class="btn btn-red btn-sm">🗑</a></td>
    </tr>{% endfor %}</tbody>
  </table></div>
  {% else %}<div class="empty">No expenses found.</div>{% endif %}
</div>""")

BUDGETS_PAGE = BASE.replace("{% block content %}{% endblock %}", """
<div class="page-title">Monthly Budgets</div>
<div class="page-sub">Set spending limits per category</div>
<div class="grid-2">
  <div class="card"><div class="section-title">Set a Budget</div>
    <form method="POST">
      <div class="form-group"><label>Category</label>
        <select name="category" required>
          {% for cat in categories %}<option>{{ cat }}</option>{% endfor %}
        </select></div>
      <div class="form-group"><label>Monthly Limit (₹)</label>
        <input type="number" name="limit" placeholder="e.g. 5000" min="1" step="1" required></div>
      <button type="submit" class="btn btn-primary btn-full mt8">🎯 Set Budget</button>
    </form>
  </div>
  <div class="card"><div class="section-title">Your Budgets</div>
    {% if budgets %}
      {% for cat,limit in budgets.items() %}
      <div class="flex-between" style="padding:10px 0;border-bottom:1px solid var(--border)">
        <div><div style="font-weight:500;font-size:.9rem">{{ cat }}</div>
          <div style="font-size:.8rem;color:var(--muted)">₹{{ "%.0f"|format(limit) }} / month</div></div>
        <a href="/delete_budget/{{ cat|urlencode }}"
           onclick="return confirm('Remove this budget?')"
           class="btn btn-red btn-sm">✕</a>
      </div>
      {% endfor %}
    {% else %}<div class="empty">No budgets set yet.</div>{% endif %}
  </div>
</div>""")

CHARTS_PAGE = BASE.replace("{% block content %}{% endblock %}", """
<div class="flex-between">
  <div><div class="page-title">Charts & Analytics</div>
    <div class="page-sub">{{ month_label }}</div></div>
  <div class="flex gap8">
    <a href="?month={{ prev_month }}" class="btn btn-ghost btn-sm">‹ Prev</a>
    <a href="?month={{ next_month }}" class="btn btn-ghost btn-sm">Next ›</a>
  </div>
</div>
<div class="grid-2 mt16">
  <div class="card"><div class="section-title">Spending Breakdown</div>
    {% if by_cat %}
    <div class="donut-wrap">
      <div class="donut">
        <svg width="120" height="120" viewBox="0 0 42 42">
          <circle cx="21" cy="21" r="15.9" fill="transparent" stroke="var(--card2)" stroke-width="6"/>
          {% set ns=namespace(off=25) %}
          {% for cat,amt in by_cat|dictsort(by='value',reverse=true) %}
            {% set pct=(amt/total*100) if total>0 else 0 %}
            {% set ci=loop.index0 % colors|length %}
            <circle cx="21" cy="21" r="15.9" fill="transparent"
              stroke="{{ colors[ci] }}" stroke-width="6"
              stroke-dasharray="{{ pct }} {{ 100-pct }}"
              stroke-dashoffset="{{ ns.off }}"/>
            {% set ns.off=ns.off-pct %}
          {% endfor %}
        </svg>
        <div class="donut-center">
          <div class="big">₹{{ "%.0f"|format(total) }}</div>
          <div class="sm">total</div>
        </div>
      </div>
      <div class="legend">
        {% for cat,amt in by_cat|dictsort(by='value',reverse=true) %}
          {% set ci=loop.index0 % colors|length %}
          <div class="legend-item">
            <div class="legend-dot" style="background:{{ colors[ci] }}"></div>
            <span style="color:var(--muted)">{{ cat }}</span>
            <span style="font-weight:600;margin-left:4px">₹{{ "%.0f"|format(amt) }}</span>
          </div>
        {% endfor %}
      </div>
    </div>
    {% else %}<div class="empty">No data for this month.</div>{% endif %}
  </div>
  <div class="card"><div class="section-title">Daily Spending</div>
    {% if daily %}
      {% set max_d=daily.values()|max %}
      {% for day,amt in daily|dictsort %}
        {% set pct=(amt/max_d*100)|int if max_d>0 else 0 %}
        <div class="bar-row" style="margin-bottom:5px">
          <div class="bar-label" style="width:48px;font-size:.75rem">{{ day[8:] }}</div>
          <div class="bar-track" style="height:17px">
            <div class="bar-fill" style="width:{{ pct }}%;background:#7c5cfc;font-size:.68rem">
              {% if pct>25 %}₹{{ "%.0f"|format(amt) }}{% endif %}</div>
          </div>
          <div class="bar-amt" style="font-size:.75rem">
            {% if pct<=25 %}₹{{ "%.0f"|format(amt) }}{% endif %}</div>
        </div>
      {% endfor %}
    {% else %}<div class="empty">No daily data.</div>{% endif %}
  </div>
</div>
<div class="card mt16"><div class="section-title">Category Comparison</div>
  {% if by_cat %}
    {% set max_val=by_cat.values()|max %}
    {% for cat,amt in by_cat|dictsort(by='value',reverse=true) %}
      {% set pct=(amt/max_val*100)|int if max_val>0 else 0 %}
      {% set ci=loop.index0 % colors|length %}
      <div class="bar-row">
        <div class="bar-label">{{ cat }}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:{{ pct }}%;background:{{ colors[ci] }}">{{ pct }}%</div>
        </div>
        <div class="bar-amt">₹{{ "%.0f"|format(amt) }}</div>
      </div>
    {% endfor %}
  {% else %}<div class="empty">No data for this month.</div>{% endif %}
</div>""")

# ══════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════
@app.route("/login", methods=["GET","POST"])
def login():
    if "username" in session: return redirect(url_for("dashboard"))
    flash, ft = None, None
    if request.method == "POST":
        u = request.form["username"].strip().lower()
        p = request.form["password"]
        if user_exists(u) and verify_user(u, p):
            session["username"] = u
            return redirect(url_for("dashboard"))
        flash = "⚠ Invalid username or password."; ft = "err"
    return render(AUTH_LOGIN, page="login", flash=flash, flash_type=ft, session_user=None)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if "username" in session: return redirect(url_for("dashboard"))
    flash, ft = None, None
    if request.method == "POST":
        u = request.form["username"].strip().lower()
        p = request.form["password"]
        c = request.form["confirm"]
        if len(u) < 3:      flash = "⚠ Username needs 3+ characters."; ft = "err"
        elif len(p) < 4:    flash = "⚠ Password needs 4+ characters."; ft = "err"
        elif p != c:        flash = "⚠ Passwords don't match."; ft = "err"
        elif user_exists(u):flash = "⚠ Username already taken."; ft = "err"
        else:
            create_user(u, p)
            session["username"] = u
            return redirect(url_for("dashboard"))
    return render(AUTH_SIGNUP, page="signup", flash=flash, flash_type=ft, session_user=None)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    u  = session["username"]
    mk = request.args.get("month", datetime.date.today().strftime("%Y-%m"))
    all_exp = get_expenses(u)
    total, by_cat = month_summary(all_exp, mk)
    month_exp = [e for e in all_exp if str(e["date"])[:7] == mk]
    count   = len(month_exp)
    days    = max(1, int(datetime.date.today().strftime("%d"))
                  if mk == datetime.date.today().strftime("%Y-%m") else 30)
    top_cat = max(by_cat, key=by_cat.get) if by_cat else None
    dt = datetime.datetime.strptime(mk+"-01", "%Y-%m-%d")
    pm, nm = get_nav_months(mk)
    return render(DASHBOARD, page="dashboard",
        month_label=dt.strftime("%B %Y"), total=total, by_cat=by_cat,
        count=count, avg_day=total/days,
        top_cat=top_cat, top_amt=by_cat.get(top_cat,0) if top_cat else 0,
        recent=sorted(month_exp, key=lambda x:x["date"], reverse=True)[:8],
        budgets=get_budgets(u), prev_month=pm, next_month=nm)

@app.route("/add", methods=["GET","POST"])
@login_required
def add():
    flash, ft = None, None
    if request.method == "POST":
        try:
            exp = {
                "id":          str(int(datetime.datetime.now().timestamp()*1000)),
                "amount":      float(request.form["amount"]),
                "date":        request.form["date"],
                "description": request.form["description"].strip(),
                "category":    request.form["category"],
                "payment":     request.form.get("payment","Cash"),
                "note":        request.form.get("note","").strip(),
            }
            add_expense(session["username"], exp)
            flash = f"✔ '{exp['description']}' saved!"; ft = "ok"
        except Exception as e:
            flash = f"Error: {e}"; ft = "err"
    return render(ADD_PAGE, page="add", flash=flash, flash_type=ft,
        categories=CATEGORIES,
        today=datetime.date.today().strftime("%Y-%m-%d"))

@app.route("/expenses")
@login_required
def expenses():
    fm = request.args.get("month","")
    fc = request.args.get("category","")
    exps = get_expenses(session["username"], month=fm, category=fc)
    return render(EXPENSES_PAGE, page="expenses",
        expenses=exps, categories=CATEGORIES,
        total_count=len(exps),
        grand_total=sum(e["amount"] for e in exps),
        filter_month=fm, filter_cat=fc)

@app.route("/delete/<eid>")
@login_required
def delete(eid):
    delete_expense(session["username"], eid)
    return redirect(url_for("expenses"))

@app.route("/budgets", methods=["GET","POST"])
@login_required
def budgets():
    flash, ft = None, None
    u = session["username"]
    if request.method == "POST":
        cat   = request.form["category"]
        limit = float(request.form["limit"])
        set_budget(u, cat, limit)
        flash = f"✔ Budget set: {cat} → ₹{limit:.0f}/month"; ft = "ok"
    return render(BUDGETS_PAGE, page="budgets",
        flash=flash, flash_type=ft,
        categories=CATEGORIES, budgets=get_budgets(u))

@app.route("/delete_budget/<category>")
@login_required
def delete_budget(category):
    from urllib.parse import unquote
    delete_budget_db(session["username"], unquote(category))
    return redirect(url_for("budgets"))

@app.route("/charts")
@login_required
def charts():
    u  = session["username"]
    mk = request.args.get("month", datetime.date.today().strftime("%Y-%m"))
    all_exp = get_expenses(u)
    total, by_cat = month_summary(all_exp, mk)
    daily = {}
    for e in all_exp:
        if str(e["date"])[:7] == mk:
            daily[str(e["date"])] = daily.get(str(e["date"]),0) + e["amount"]
    dt = datetime.datetime.strptime(mk+"-01", "%Y-%m-%d")
    pm, nm = get_nav_months(mk)
    return render(CHARTS_PAGE, page="charts",
        month_label=dt.strftime("%B %Y"), total=total,
        by_cat=by_cat, daily=daily, prev_month=pm, next_month=nm)

@app.route("/export")
@login_required
def export():
    exps = get_expenses(session["username"])
    out  = io.StringIO()
    w    = csv.DictWriter(out,
        fieldnames=["date","description","category","amount","payment","note"])
    w.writeheader()
    for e in exps:
        w.writerow({"date":e["date"],"description":e["description"],
                    "category":e["category"],"amount":e["amount"],
                    "payment":e.get("payment",""),"note":e.get("note","")})
    resp = make_response(out.getvalue())
    resp.headers["Content-Disposition"] = \
        f"attachment; filename={session['username']}_expenses_{datetime.date.today()}.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp

# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════
init_db()

if __name__ == "__main__":
    try: local_ip = socket.gethostbyname(socket.gethostname())
    except: local_ip = "127.0.0.1"
    print("\n" + "="*52)
    print("  💸  EXPENSE TRACKER  —  PostgreSQL Edition")
    print("="*52)
    print(f"  Desktop  →  http://localhost:5000")
    print(f"  Mobile   →  http://{local_ip}:5000")
    print(f"  DB mode  →  {'PostgreSQL' if DATABASE_URL else 'SQLite (local)'}")
    print("="*52 + "\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
