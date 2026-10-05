"""Short SQLite transactions; all API calls run these methods in a thread.

One Railway replica / one ASGI worker. Persistent volume required in production.
"""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.models import SessionMemory


class RateExceeded(Exception):
    pass


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Database schema is newer than this application")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, memory TEXT NOT NULL, created REAL NOT NULL, touched REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              role TEXT NOT NULL, content TEXT NOT NULL, action TEXT, created REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id);
            CREATE TABLE IF NOT EXISTS chat_requests (
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, request_id TEXT NOT NULL,
              input TEXT NOT NULL, events TEXT NOT NULL, created REAL NOT NULL,
              PRIMARY KEY(session_id, request_id)
            );
            CREATE TABLE IF NOT EXISTS leads (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL,
              phone TEXT NOT NULL, name TEXT, service TEXT, notes TEXT NOT NULL,
              consent_at REAL NOT NULL, consent_text TEXT NOT NULL, language TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'new', created REAL NOT NULL, updated REAL NOT NULL,
              UNIQUE(session_id, request_id)
            );
            CREATE INDEX IF NOT EXISTS leads_created ON leads(created);
            CREATE INDEX IF NOT EXISTS leads_dedup ON leads(session_id, phone);
            CREATE TABLE IF NOT EXISTS outbox (
              lead_id TEXT PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
              status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
              next_attempt REAL NOT NULL, lease_until REAL, last_error TEXT, sent_at REAL
            );
            CREATE TABLE IF NOT EXISTS rate_limits (
              key TEXT NOT NULL, bucket INTEGER NOT NULL, count INTEGER NOT NULL,
              expires REAL NOT NULL, PRIMARY KEY(key, bucket)
            );
            CREATE TABLE IF NOT EXISTS errors (
              id INTEGER PRIMARY KEY, code TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
              id INTEGER PRIMARY KEY, model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL,
              completion_tokens INTEGER NOT NULL, created REAL NOT NULL
            );
            PRAGMA user_version=1;
            """)

    def create_session(self, sid: str):
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)", (sid, SessionMemory().model_dump_json(), now, now)
            )

    def load_session(self, sid: str) -> SessionMemory | None:
        with self.connection() as conn:
            row = conn.execute("SELECT memory FROM sessions WHERE id=?", (sid,)).fetchone()
            return SessionMemory.model_validate_json(row[0]) if row else None

    def history(self, sid: str, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT role,content,action FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (sid, limit),
            ).fetchall()
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "action": json.loads(r["action"]) if r["action"] else None,
            }
            for r in reversed(rows)
        ]

    def cached_chat(self, sid: str, rid: str):
        with self.connection() as conn:
            r = conn.execute(
                "SELECT input,events FROM chat_requests WHERE session_id=? AND request_id=?", (sid, rid)
            ).fetchone()
            return (r["input"], json.loads(r["events"])) if r else None

    def save_turn(
        self, sid: str, rid: str, message: str, reply: str, memory: SessionMemory, events: list[dict]
    ):
        now = time.time()
        action = next((e for e in events if e["type"] == "action"), None)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE sessions SET memory=?,touched=? WHERE id=?", (memory.model_dump_json(), now, sid)
            )
            conn.executemany(
                "INSERT INTO messages(session_id,role,content,action,created) VALUES(?,?,?,?,?)",
                [
                    (sid, "user", message, None, now),
                    (sid, "assistant", reply, json.dumps(action) if action else None, now),
                ],
            )
            conn.execute(
                "INSERT INTO chat_requests VALUES(?,?,?,?,?)", (sid, rid, message, json.dumps(events), now)
            )

    def consume_limits(self, specs: list[tuple[str, int, int]]):
        """Atomic fixed windows. Keys contain keyed IP hashes, never raw IPs."""
        now = time.time()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for key, seconds, maximum in specs:
                bucket = int(now) // seconds
                row = conn.execute(
                    "SELECT count FROM rate_limits WHERE key=? AND bucket=?", (key, bucket)
                ).fetchone()
                if row and row[0] >= maximum:
                    raise RateExceeded()
                conn.execute(
                    "INSERT INTO rate_limits VALUES(?,?,1,?) ON CONFLICT(key,bucket) DO UPDATE SET count=count+1",
                    (key, bucket, (bucket + 1) * seconds),
                )

    def save_lead(self, sid: str, rid: str, phone: str, name: str | None, consent_text: str):
        now = time.time()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM leads WHERE session_id=? AND request_id=?", (sid, rid)
            ).fetchone()
            if existing:
                if existing["phone"] != phone or existing["name"] != name:
                    raise ValueError("Request ID was already used with different details")
                return dict(existing), True
            # Double submission with a different request ID must not send another notification.
            existing = conn.execute(
                "SELECT * FROM leads WHERE session_id=? AND phone=? AND created>? ORDER BY created DESC LIMIT 1",
                (sid, phone, now - 86400),
            ).fetchone()
            if existing:
                return dict(existing), True
            row = conn.execute("SELECT memory FROM sessions WHERE id=?", (sid,)).fetchone()
            if not row:
                raise ValueError("Session expired")
            memory = SessionMemory.model_validate_json(row[0])
            lid = str(uuid.uuid4())
            state = memory.state
            conn.execute(
                "INSERT INTO leads(id,session_id,request_id,phone,name,service,notes,consent_at,consent_text,language,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    lid,
                    sid,
                    rid,
                    phone,
                    name,
                    state.service,
                    state.summary(),
                    now,
                    consent_text,
                    state.language,
                    now,
                    now,
                ),
            )
            conn.execute("INSERT INTO outbox(lead_id,next_attempt) VALUES(?,?)", (lid, now))
            memory.lead_saved = True
            memory.state.contact_consent = True
            conn.execute(
                "UPDATE sessions SET memory=?,touched=? WHERE id=?", (memory.model_dump_json(), now, sid)
            )
            lead = conn.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
            return dict(lead), False

    def claim_notification(self):
        now = time.time()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT l.*,o.attempts FROM outbox o JOIN leads l ON l.id=o.lead_id WHERE (o.status='pending' AND o.next_attempt<=?) OR (o.status='sending' AND o.lease_until<=?) ORDER BY o.next_attempt LIMIT 1",
                (now, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE outbox SET status='sending',lease_until=?,attempts=attempts+1 WHERE lead_id=?",
                (now + 60, row["id"]),
            )
            return dict(row) | {"attempts": row["attempts"] + 1}

    def notification_result(
        self, lid: str, *, sent: bool, error: str = "", retry_seconds: float = 30, dead: bool = False
    ):
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                "UPDATE outbox SET status=?,next_attempt=?,lease_until=NULL,last_error=?,sent_at=? WHERE lead_id=?",
                (
                    "sent" if sent else "dead" if dead else "pending",
                    now + retry_seconds,
                    error[:100] or None,
                    now if sent else None,
                    lid,
                ),
            )

    def retry_notification(self, lid: str):
        with self.connection() as conn:
            row = conn.execute("SELECT status FROM outbox WHERE lead_id=?", (lid,)).fetchone()
            if not row:
                return False
            if row[0] == "sending":
                raise ValueError("Notification is currently being sent")
            if row[0] == "sent":
                raise ValueError("Notification has already been delivered")
            conn.execute(
                "UPDATE outbox SET status='pending',attempts=0,next_attempt=?,lease_until=NULL,last_error=NULL WHERE lead_id=?",
                (time.time(), lid),
            )
            return True

    def leads(self, limit: int = 50, offset: int = 0):
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT l.*,o.status AS notification_status,o.attempts,o.last_error,o.sent_at FROM leads l JOIN outbox o ON o.lead_id=l.id ORDER BY l.created DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT count(*) FROM leads").fetchone()[0]
        return {"items": [dict(r) for r in rows], "total": total}

    def update_lead(self, lid: str, status: str):
        with self.connection() as conn:
            return (
                conn.execute(
                    "UPDATE leads SET status=?,updated=? WHERE id=?", (status, time.time(), lid)
                ).rowcount
                > 0
            )

    def delete_lead(self, lid: str):
        with self.connection() as conn:
            row = conn.execute("SELECT session_id FROM leads WHERE id=?", (lid,)).fetchone()
            if not row:
                return False
            # Remove the enquiry's complete conversation as well as its contact record.
            conn.execute("DELETE FROM sessions WHERE id=?", (row[0],))
            conn.execute("DELETE FROM leads WHERE session_id=?", (row[0],))
            return True

    def error(self, code: str):
        with self.connection() as conn:
            conn.execute("INSERT INTO errors(code,created) VALUES(?,?)", (code[:100], time.time()))

    def record_usage(self, model: str, usage: dict):
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO usage(model,prompt_tokens,completion_tokens,created) VALUES(?,?,?,?)",
                (
                    model,
                    int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)),
                    time.time(),
                ),
            )

    def summary(self):
        with self.connection() as conn:
            return {
                "leads": conn.execute("SELECT count(*) FROM leads").fetchone()[0],
                "open_leads": conn.execute("SELECT count(*) FROM leads WHERE status='new'").fetchone()[0],
                "pending_notifications": conn.execute(
                    "SELECT count(*) FROM outbox WHERE status IN ('pending','sending')"
                ).fetchone()[0],
                "failed_notifications": conn.execute(
                    "SELECT count(*) FROM outbox WHERE status='dead'"
                ).fetchone()[0],
                "errors_24h": conn.execute(
                    "SELECT count(*) FROM errors WHERE created>?", (time.time() - 86400,)
                ).fetchone()[0],
                "usage": [
                    dict(r)
                    for r in conn.execute(
                        "SELECT model,sum(prompt_tokens) AS prompt_tokens,sum(completion_tokens) AS completion_tokens FROM usage WHERE created>? GROUP BY model",
                        (time.time() - 30 * 86400,),
                    )
                ],
            }

    def cleanup(self, conversation_days: int, lead_days: int):
        now = time.time()
        with self.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE touched<?", (now - conversation_days * 86400,))
            conn.execute("DELETE FROM leads WHERE created<?", (now - lead_days * 86400,))
            conn.execute("DELETE FROM rate_limits WHERE expires<?", (now,))
            conn.execute("DELETE FROM errors WHERE created<?", (now - 30 * 86400,))
            conn.execute("DELETE FROM usage WHERE created<?", (now - 90 * 86400,))

    def backup(self, destination: Path):
        with self.connection() as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        destination.chmod(0o600)

    def ready(self):
        with self.connection() as conn:
            conn.execute("SELECT 1 FROM sessions LIMIT 1")
        return True
