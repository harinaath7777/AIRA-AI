# database.py
# SQLite layer for research history, saved research, followups, and comparisons.
# All user-data tables are scoped by user_id (added lazily via migration).

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "research.db"


def get_connection():
    """Return a thread-safe SQLite connection with row_factory."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they do not exist, and run migrations."""
    conn = get_connection()
    c = conn.cursor()

    # ─── Research History ──────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL DEFAULT 0,
            query       TEXT NOT NULL,
            mode        TEXT NOT NULL DEFAULT 'normal',
            result_json TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)

    # ─── Saved Research ───────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS saved (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL DEFAULT 0,
            history_id  INTEGER NOT NULL,
            tag         TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (history_id) REFERENCES history(id) ON DELETE CASCADE
        )
    """)

    # ─── Comparison Results ───────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS comparisons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL DEFAULT 0,
            topic_a     TEXT NOT NULL,
            topic_b     TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)

    # ─── Follow-up threads ────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS followups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id  INTEGER NOT NULL,
            question    TEXT NOT NULL,
            answer_json TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (history_id) REFERENCES history(id) ON DELETE CASCADE
        )
    """)

    conn.commit()

    # ── Schema migrations: add user_id columns if missing ─────────
    for table, col in [("history", "user_id"), ("saved", "user_id"), ("comparisons", "user_id")]:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.close()


# ─────────────────────────────────────────────────────────────
# HISTORY OPERATIONS
# ─────────────────────────────────────────────────────────────

def save_history(query, mode, result, user_id=0):
    """Persist a research result and return its new row id."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO history (user_id, query, mode, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, query, mode, json.dumps(result, ensure_ascii=False), now),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_history(limit=50, user_id=0):
    """Return recent history rows for a user, most-recent first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, query, mode, created_at FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_item(history_id, user_id=0):
    """Return a single history item (user must own it, or user_id=0 for legacy)."""
    conn = get_connection()
    if user_id:
        row = conn.execute(
            "SELECT * FROM history WHERE id = ? AND user_id = ?", (history_id, user_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM history WHERE id = ?", (history_id,)
        ).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["result"] = json.loads(item.pop("result_json"))
    return item


def get_all_history_for_export(user_id=0):
    """Return all history items with parsed results for bulk export."""
    conn = get_connection()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM history WHERE user_id = ? ORDER BY id ASC", (user_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM history ORDER BY id ASC").fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["result"] = json.loads(d.pop("result_json"))
        except Exception:
            d["result"] = {"query": d.get("query", ""), "summary": "Error parsing result"}
        items.append(d)
    return items


def delete_history_item(history_id, user_id=0):
    """Delete a history item (cascade deletes followups and saved entries)."""
    conn = get_connection()
    if user_id:
        conn.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (history_id, user_id))
    else:
        conn.execute("DELETE FROM history WHERE id = ?", (history_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────
# SAVED RESEARCH OPERATIONS
# ─────────────────────────────────────────────────────────────

def save_research(history_id, tag="", user_id=0):
    """Mark a history item as saved."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    existing = conn.execute(
        "SELECT id FROM saved WHERE history_id = ? AND user_id = ?", (history_id, user_id)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO saved (user_id, history_id, tag, created_at) VALUES (?, ?, ?, ?)",
            (user_id, history_id, tag, now),
        )
        conn.commit()
    conn.close()


def get_saved(user_id=0):
    """Return all saved research items for a user, joined with history."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.id, s.history_id, s.tag, s.created_at,
               h.query, h.mode
        FROM saved s
        JOIN history h ON h.id = s.history_id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def unsave_research(history_id, user_id=0):
    """Remove a saved entry."""
    conn = get_connection()
    if user_id:
        conn.execute("DELETE FROM saved WHERE history_id = ? AND user_id = ?", (history_id, user_id))
    else:
        conn.execute("DELETE FROM saved WHERE history_id = ?", (history_id,))
    conn.commit()
    conn.close()


def is_saved(history_id, user_id=0):
    """Check if a history item is saved."""
    conn = get_connection()
    if user_id:
        row = conn.execute(
            "SELECT id FROM saved WHERE history_id = ? AND user_id = ?", (history_id, user_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM saved WHERE history_id = ?", (history_id,)
        ).fetchone()
    conn.close()
    return row is not None


# ─────────────────────────────────────────────────────────────
# COMPARISON OPERATIONS
# ─────────────────────────────────────────────────────────────

def save_comparison(topic_a, topic_b, result, user_id=0):
    """Save a comparison result and return its id."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO comparisons (user_id, topic_a, topic_b, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, topic_a, topic_b, json.dumps(result, ensure_ascii=False), now),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_comparisons(limit=20, user_id=0):
    """Return recent comparisons for a user."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, topic_a, topic_b, created_at FROM comparisons WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_comparison(cmp_id, user_id=0):
    """Return a single comparison with full result."""
    conn = get_connection()
    if user_id:
        row = conn.execute(
            "SELECT * FROM comparisons WHERE id = ? AND user_id = ?", (cmp_id, user_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM comparisons WHERE id = ?", (cmp_id,)
        ).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["result"] = json.loads(item.pop("result_json"))
    return item


# ─────────────────────────────────────────────────────────────
# FOLLOW-UP OPERATIONS
# ─────────────────────────────────────────────────────────────

def save_followup(history_id, question, answer):
    """Save a follow-up Q&A under a history item."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO followups (history_id, question, answer_json, created_at) VALUES (?, ?, ?, ?)",
        (history_id, question, json.dumps(answer, ensure_ascii=False), now),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_followups(history_id):
    """Return all follow-ups for a history item."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM followups WHERE history_id = ? ORDER BY id ASC",
        (history_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        item["answer"] = json.loads(item.pop("answer_json"))
        result.append(item)
    return result


# Auto-init on import
init_db()
