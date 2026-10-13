"""Capa de base de datos (SQLite). Guarda cuentas de Google, proyectos e informes."""
import sqlite3
import json
from datetime import datetime
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT UNIQUE NOT NULL,
    token_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,              -- nombre de la web / cliente
    domain       TEXT NOT NULL,              -- https://dominio.com/
    account_id   INTEGER,                    -- cuenta de Google que da acceso
    ga4_property TEXT,                        -- 'properties/123456'
    ga4_name     TEXT,
    gsc_site     TEXT,                        -- 'sc-domain:dominio.com' o URL
    competitors  TEXT,                        -- JSON: lista de dominios
    created_at   TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    filename     TEXT NOT NULL,
    period_start TEXT,
    period_end   TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Cuentas de Google ----------
def upsert_account(email: str, token_json: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO accounts (email, token_json, created_at) VALUES (?,?,?) "
        "ON CONFLICT(email) DO UPDATE SET token_json=excluded.token_json",
        (email, token_json, _now()),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM accounts WHERE email=?", (email,)).fetchone()
    conn.close()
    return row["id"]


def list_accounts():
    conn = get_db()
    rows = conn.execute("SELECT * FROM accounts ORDER BY email").fetchall()
    conn.close()
    return rows


def get_account(account_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()
    return row


def delete_account(account_id: int):
    conn = get_db()
    conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()


# ---------- Proyectos ----------
def create_project(name, domain, account_id, ga4_property, ga4_name, gsc_site, competitors):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO projects (name, domain, account_id, ga4_property, ga4_name, gsc_site, competitors, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (name, domain, account_id, ga4_property, ga4_name, gsc_site,
         json.dumps(competitors or []), _now()),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def update_project(pid, **fields):
    if not fields:
        return
    if "competitors" in fields:
        fields["competitors"] = json.dumps(fields["competitors"] or [])
    cols = ", ".join(f"{k}=?" for k in fields)
    conn = get_db()
    conn.execute(f"UPDATE projects SET {cols} WHERE id=?", (*fields.values(), pid))
    conn.commit()
    conn.close()


def list_projects():
    conn = get_db()
    rows = conn.execute(
        "SELECT p.*, a.email AS account_email FROM projects p "
        "LEFT JOIN accounts a ON a.id = p.account_id ORDER BY p.name"
    ).fetchall()
    conn.close()
    return rows


def get_project(pid):
    conn = get_db()
    row = conn.execute(
        "SELECT p.*, a.email AS account_email FROM projects p "
        "LEFT JOIN accounts a ON a.id = p.account_id WHERE p.id=?",
        (pid,),
    ).fetchone()
    conn.close()
    return row


def delete_project(pid):
    conn = get_db()
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()


def project_competitors(row):
    try:
        return json.loads(row["competitors"] or "[]")
    except Exception:
        return []


# ---------- Informes generados ----------
def add_report(project_id, filename, period_start, period_end):
    conn = get_db()
    conn.execute(
        "INSERT INTO reports (project_id, filename, period_start, period_end, created_at) VALUES (?,?,?,?,?)",
        (project_id, filename, period_start, period_end, _now()),
    )
    conn.commit()
    conn.close()


def list_reports(project_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM reports WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    conn.close()
    return rows
