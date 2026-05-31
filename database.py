import sqlite3
import os
import json
from datetime import datetime

USE_MEMORY = False
DB_PATH = os.path.join(os.path.dirname(__file__), 'kesit_tayini.db')
_conn = None

DEFAULT_CONFIG = {
    "MESKEN_UNIT_KW": 2.0,
    "TICARET_UNIT_KW": 5.0,
    "THRESHOLD_LIMIT": 100,
    "VOLTAGE_DROP_LIMIT": 5.0,
    "CONDUCTIVITY_COPPER": 56,
    "CONDUCTIVITY_ALUMINUM": 35,
    "VOLTAGE": 380,
    "COS_PHI": 0.8
}

def get_conn():
    global _conn
    if _conn is None:
        if USE_MEMORY:
            _conn = sqlite3.connect(':memory:', check_same_thread=False)
        else:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return _conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            p REAL,
            l REAL,
            cable TEXT,
            e REAL,
            i REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            config_json TEXT
        )
    ''')
    c.execute('SELECT COUNT(*) FROM settings')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO settings (id, config_json) VALUES (1, ?)', (json.dumps(DEFAULT_CONFIG),))
    conn.commit()

def add_history_entry(p, l, cable, e, i):
    conn = get_conn()
    c = conn.cursor()
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    c.execute('''
        INSERT INTO history (date, p, l, cable, e, i)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date_str, p, l, cable, e, i))
    conn.commit()

def get_history():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 50')
    rows = c.fetchall()
    return [dict(row) for row in rows]

def get_config():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT config_json FROM settings WHERE id = 1')
    row = c.fetchone()
    if row:
        return json.loads(row[0])
    return DEFAULT_CONFIG

def update_config(new_config):
    current = get_config()
    current.update(new_config)
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE settings SET config_json = ? WHERE id = 1', (json.dumps(current),))
    conn.commit()
    return current
