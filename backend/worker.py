import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from .config import settings
from .db import TERMINAL, claim_file, connect, update_file
from .transcripts import output_path


def remove_recording(file_id):
    shutil.rmtree(settings.data / "recordings" / file_id, ignore_errors=True)


def recover():
    with connect() as db:
        # Only fully uploaded submissions can resume. Incomplete HTTP uploads cannot.
        interrupted = db.execute("SELECT id FROM files WHERE status='uploading'").fetchall()
        for row in interrupted:
            remove_recording(row["id"])
            db.execute("DELETE FROM files WHERE id=?", (row["id"],))
        db.execute("""UPDATE files SET status='queued', stage='Queued after restart', progress=NULL,
                   eta_seconds=NULL WHERE status='processing'""")
        terminal = db.execute("SELECT id FROM files WHERE status IN ('completed','failed','cancelled')").fetchall()
        known = {row["id"] for row in db.execute("SELECT id FROM files")}
    for row in terminal:
        remove_recording(row["id"])
    for path in (settings.data / "recordings").iterdir():
        if path.name not in known:
            shutil.rmtree(path, ignore_errors=True)


def cleanup_abandoned():
    with connect() as db:
        rows = db.execute(
            "SELECT id FROM jobs WHERE state='uploading' AND updated_at<?", (time.time() - settings.upload_ttl,)
        ).fetchall()
        for row in rows:
            for file in db.execute("SELECT id FROM files WHERE job_id=?", (row["id"],)):
                remove_recording(file["id"])
            db.execute("DELETE FROM jobs WHERE id=?", (row["id"],))


class Worker:
    def __init__(self):
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="transcription-queue")

    def start(self):
        recover()
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=15)

    @staticmethod
    def terminate(process):
        # Include ffmpeg children. No orphan inference processes on cancellation/shutdown.
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()

    def loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception as error:  # noqa: BLE001 - keep the queue alive after recoverable I/O errors
                print(f"Queue error ({type(error).__name__}); retrying.", file=sys.stderr)
            self.stop.wait(1)

    def maintain(self):
        cleanup_abandoned()
        with connect() as db:
            cancelled = db.execute("""SELECT files.id FROM files JOIN jobs ON jobs.id=files.job_id
                WHERE jobs.cancel_requested=1 AND files.status IN ('queued','uploaded')""").fetchall()
            for row in cancelled:
                db.execute(
                    "UPDATE files SET status='cancelled',stage='Cancelled',finished_at=? WHERE id=?",
                    (time.time(), row["id"]),
                )
                remove_recording(row["id"])

    def tick(self):
        self.maintain()
        file = claim_file()
        if file is None:
            return
        try:
            process = subprocess.Popen([sys.executable, "-m", "backend.engine", file["id"]], start_new_session=True)
        except OSError:
            update_file(
                file["id"],
                status="failed",
                stage="Failed",
                eta_seconds=None,
                error="Could not start the transcription worker. Upload again after freeing server resources.",
                finished_at=time.time(),
            )
            remove_recording(file["id"])
            return
        cancelled = False
        while process.poll() is None:
            # Other jobs can be cancelled/expired while a long recording is running.
            self.maintain()
            with connect() as db:
                job = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (file["job_id"],)).fetchone()
            cancelled = bool(job and job["cancel_requested"])
            if self.stop.is_set() or cancelled:
                self.terminate(process)
                break
            self.stop.wait(1)
        if self.stop.is_set() and not cancelled:
            with connect() as db:
                db.execute(
                    """UPDATE files SET status='queued',stage='Queued after restart',progress=NULL,
                           eta_seconds=NULL WHERE id=? AND status='processing'""",
                    (file["id"],),
                )
            return
        with connect() as db:
            current = db.execute("SELECT status FROM files WHERE id=?", (file["id"],)).fetchone()
        if current["status"] not in TERMINAL:
            update_file(
                file["id"],
                status="cancelled" if cancelled else "failed",
                stage="Cancelled" if cancelled else "Failed",
                progress=None,
                eta_seconds=None,
                has_transcript=int(output_path(file["id"], "txt").exists()),
                error=None
                if cancelled
                else "Worker exited unexpectedly, possibly due to memory pressure. Try the small model.",
                finished_at=time.time(),
            )
        remove_recording(file["id"])
