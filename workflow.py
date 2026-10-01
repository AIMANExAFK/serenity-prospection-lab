"""Offline workflow: synthetic contacts and simulated events only."""
import csv
from datetime import datetime, timedelta, timezone
import re
import sqlite3


def connect(path=':memory:'):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS contacts (
            email TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','drafted','simulated','replied','opted_out')),
            subject TEXT,
            body TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE REFERENCES contacts(email),
            domain TEXT NOT NULL,
            simulated_at TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind='simulated')
        );
    ''')
    return db


def normalize_email(value):
    email = value.strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[a-z0-9][a-z0-9._+\-]*@(?:[a-z0-9][a-z0-9\-]*\.)+invalid', email):
        raise ValueError('Only synthetic .invalid addresses are accepted')
    return email


def import_csv(db, stream):
    reader = csv.DictReader(stream)
    if not {'email', 'company'}.issubset(reader.fieldnames or []):
        raise ValueError('Required columns: email, company')
    rows = []
    for row in reader:
        email = normalize_email(row.get('email') or '')
        company = (row.get('company') or '').strip()
        if not company or len(company) > 120 or any(c in company for c in '\r\n'):
            raise ValueError('Invalid company')
        rows.append((email, company))
    before = db.total_changes
    with db:
        db.executemany("INSERT OR IGNORE INTO contacts(email,company,status) VALUES (?,?,'pending')", rows)
    return db.total_changes - before


def draft(db):
    rows = db.execute("SELECT email, company FROM contacts WHERE status='pending' ORDER BY email").fetchall()
    with db:
        for row in rows:
            db.execute("UPDATE contacts SET subject=?, body=?, status='drafted' WHERE email=?", (
                f"Démonstration pour {row['company']}",
                f"Bonjour, ceci est un brouillon de test pour {row['company']}. Aucun email ne sera envoyé.",
                row['email'],
            ))
    return len(rows)


def suppress(db, email, status='opted_out'):
    if status not in ('opted_out', 'replied'):
        raise ValueError('Unknown suppression status')
    with db:
        result = db.execute('UPDATE contacts SET status=? WHERE email=?', (status, normalize_email(email)))
    return result.rowcount


def simulate(db, now, daily_limit=2, spacing_seconds=90):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('A timezone-aware datetime is required')
    if not isinstance(daily_limit, int) or isinstance(daily_limit, bool) or not 1 <= daily_limit <= 20:
        raise ValueError('Daily limit must be an integer between 1 and 20')
    if not isinstance(spacing_seconds, int) or spacing_seconds < 1:
        raise ValueError('Invalid spacing')
    now = now.astimezone(timezone.utc)
    if now.weekday() >= 5 or not 9 <= now.hour < 17:
        return {'simulated': 0, 'reason': 'outside-window'}
    stamp = now.isoformat()
    day = now.date().isoformat()
    with db:
        # Reserve the local write transaction before eligibility checks.
        db.execute('BEGIN IMMEDIATE')
        latest = db.execute('SELECT MAX(simulated_at) FROM events').fetchone()[0]
        if latest and (now - datetime.fromisoformat(latest)).total_seconds() < spacing_seconds:
            return {'simulated': 0, 'reason': 'spacing'}
        count = db.execute('SELECT COUNT(*) FROM events WHERE substr(simulated_at,1,10)=?', (day,)).fetchone()[0]
        if count >= daily_limit:
            return {'simulated': 0, 'reason': 'daily-limit'}
        cutoff = (now - timedelta(days=7)).isoformat()
        rows = db.execute("SELECT email FROM contacts WHERE status='drafted' ORDER BY email").fetchall()
        for row in rows:
            domain = row['email'].split('@')[1]
            recent = db.execute('SELECT 1 FROM events WHERE domain=? AND simulated_at>? LIMIT 1', (domain, cutoff)).fetchone()
            if recent:
                continue
            db.execute("INSERT INTO events(email,domain,simulated_at,kind) VALUES (?,?,?,'simulated')", (row['email'], domain, stamp))
            db.execute("UPDATE contacts SET status='simulated' WHERE email=?", (row['email'],))
            return {'simulated': 1, 'reason': 'recorded'}
    return {'simulated': 0, 'reason': 'no-eligible-draft'}


def status(db):
    return dict(db.execute('SELECT status, COUNT(*) FROM contacts GROUP BY status').fetchall())
