import json
import sqlite3
import time
from contextlib import contextmanager

from .config import settings

TERMINAL = {"completed", "failed", "cancelled"}


@contextmanager
def connect():
    db = sqlite3.connect(settings.data / "jobs.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    settings.prepare()
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, model TEXT NOT NULL,
                diarize INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'uploading',
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                name TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'uploading', stage TEXT NOT NULL DEFAULT 'Uploading',
                progress REAL, stage_started_at REAL, eta_seconds REAL,
                duration REAL, error TEXT, warnings TEXT NOT NULL DEFAULT '[]',
                has_transcript INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, finished_at REAL
            );
            CREATE INDEX IF NOT EXISTS files_queue ON files(status, created_at);
            CREATE INDEX IF NOT EXISTS files_job ON files(job_id);
        """)


def update_file(file_id, **fields):
    if not fields:
        return
    # Field names are internal constants, never request input.
    with connect() as db:
        db.execute(
            f"UPDATE files SET {', '.join(key + '=?' for key in fields)} WHERE id=?", [*fields.values(), file_id]
        )


def serialize_job(job, files):
    result = dict(job)
    result["diarize"] = bool(result["diarize"])
    result["cancel_requested"] = bool(result["cancel_requested"])
    result["files"] = []
    for row in files:
        item = dict(row)
        item["warnings"] = json.loads(item["warnings"])
        item["has_transcript"] = bool(item["has_transcript"])
        result["files"].append(item)
    statuses = [f["status"] for f in result["files"]]
    if result["state"] == "uploading":
        status = "uploading"
    elif "processing" in statuses:
        status = "processing"
    elif "queued" in statuses:
        status = "queued"
    elif statuses and all(s == "completed" for s in statuses):
        status = "completed"
    elif "completed" in statuses or any(f["has_transcript"] for f in result["files"]):
        status = "partial"
    elif "failed" in statuses:
        status = "failed"
    else:
        status = "cancelled"
    result["status"] = status
    result["finished_files"] = sum(s in TERMINAL for s in statuses)
    return result


def get_job(job_id):
    with connect() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            return None
        files = db.execute("SELECT * FROM files WHERE job_id=? ORDER BY created_at, id", (job_id,)).fetchall()
    return serialize_job(job, files)


def claim_file():
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("""SELECT files.* FROM files JOIN jobs ON jobs.id=files.job_id
            WHERE files.status='queued' AND jobs.state='submitted' AND jobs.cancel_requested=0
            ORDER BY jobs.created_at, files.created_at, files.id LIMIT 1""").fetchone()
        if row:
            db.execute(
                """UPDATE files SET status='processing', stage='Preparing audio', progress=NULL,
                        stage_started_at=?, eta_seconds=NULL WHERE id=?""",
                (time.time(), row["id"]),
            )
            return dict(row)
    return None
