import asyncio
import io
import shutil
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .db import connect, get_job, initialize, serialize_job
from .transcripts import output_path
from .worker import Worker, remove_recording


@asynccontextmanager
async def lifespan(app):
    initialize()
    worker = Worker() if settings.worker_enabled else None
    if worker:
        worker.start()
    yield
    if worker:
        await asyncio.to_thread(worker.close)


app = FastAPI(title="Simple Transcription", lifespan=lifespan)


@app.middleware("http")
async def same_origin(request: Request, call_next):
    # Prevent another website from submitting jobs to a private-network instance.
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path in {"/", "/index.html", "/sw.js", "/offline.html", "/manifest.webmanifest"}:
        response.headers["Cache-Control"] = "no-cache"
    return response


def require_job(job_id):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


def clean_name(name):
    name = name.replace("\\", "/").split("/")[-1]
    return "".join(c for c in name if c.isprintable())[:200].strip() or "recording"


class NewJob(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    model: Literal["small", "medium"] = "small"
    diarize: bool = False


@app.get("/api/health")
def health():
    with connect() as db:
        db.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {
        "speaker_labels_available": bool(settings.hf_token),
        "max_file_bytes": settings.max_file_bytes,
        "max_files": settings.max_files,
        "max_duration_seconds": settings.max_duration,
        "language": "en",
    }


@app.get("/api/jobs")
def jobs(limit: int = 50, offset: int = 0):
    limit, offset = min(100, max(1, limit)), max(0, offset)
    with connect() as db:
        rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        result = [
            serialize_job(
                row, db.execute("SELECT * FROM files WHERE job_id=? ORDER BY created_at,id", (row["id"],)).fetchall()
            )
            for row in rows
        ]
        total = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return {"jobs": result, "total": total}


@app.post("/api/jobs", status_code=201)
def create_job(body: NewJob):
    name = "".join(c for c in body.name if c.isprintable()).strip()
    if not name:
        raise HTTPException(422, "Give this job a name.")
    if body.diarize and not settings.hf_token:
        raise HTTPException(422, "Speaker labels need HF_TOKEN configured on the server.")
    job_id, now = uuid.uuid4().hex, time.time()
    with connect() as db:
        db.execute(
            "INSERT INTO jobs(id,name,model,diarize,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (job_id, name, body.model, body.diarize, now, now),
        )
    return require_job(job_id)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    return require_job(job_id)


@app.put("/api/jobs/{job_id}/files", status_code=201)
async def upload(job_id: str, request: Request, filename: str):
    # Stream raw bytes to disk. Avoid multipart spooling and a second multi-GB copy.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > settings.max_file_bytes
        except ValueError:
            raise HTTPException(400, "Invalid upload size.")
        if too_large:
            raise HTTPException(413, "File exceeds the server upload limit.")
    file_id, now = uuid.uuid4().hex, time.time()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found.")
        if job["state"] != "uploading" or job["cancel_requested"]:
            raise HTTPException(409, "This job is no longer accepting files.")
        count = db.execute("SELECT COUNT(*) FROM files WHERE job_id=?", (job_id,)).fetchone()[0]
        if count >= settings.max_files:
            raise HTTPException(422, "Too many files in this job.")
        db.execute(
            "INSERT INTO files(id,job_id,name,created_at) VALUES (?,?,?,?)",
            (file_id, job_id, clean_name(filename), now),
        )
    directory = settings.data / "recordings" / file_id
    size, last_touch = 0, now
    try:
        directory.mkdir(parents=True)
        with (directory / "source.part").open("wb") as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.max_file_bytes:
                    raise HTTPException(413, "File exceeds the server upload limit.")
                if shutil.disk_usage(settings.data).free < len(chunk) + 256 * 1024 * 1024:
                    raise HTTPException(507, "Not enough disk space for this recording.")
                stream.write(chunk)
                if time.time() - last_touch > 5:
                    with connect() as db:
                        current = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
                        if not current or current["cancel_requested"]:
                            raise HTTPException(409, "Upload cancelled.")
                        db.execute("UPDATE jobs SET updated_at=? WHERE id=?", (time.time(), job_id))
                    last_touch = time.time()
        if size == 0:
            raise HTTPException(422, "The uploaded file is empty.")
        (directory / "source.part").replace(directory / "source")
        with connect() as db:
            current = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not current or current["cancel_requested"]:
                raise HTTPException(409, "Upload cancelled.")
            db.execute("UPDATE files SET status='uploaded', stage='Ready to queue',size=? WHERE id=?", (size, file_id))
            db.execute("UPDATE jobs SET updated_at=? WHERE id=?", (time.time(), job_id))
    except BaseException:
        remove_recording(file_id)
        with connect() as db:
            db.execute("DELETE FROM files WHERE id=?", (file_id,))
        raise
    return {"id": file_id, "size": size}


@app.post("/api/jobs/{job_id}/submit")
def submit(job_id: str):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found.")
        if job["cancel_requested"]:
            raise HTTPException(409, "Job was cancelled.")
        if job["state"] == "submitted":
            return require_job(job_id)
        files = db.execute("SELECT status FROM files WHERE job_id=?", (job_id,)).fetchall()
        if not files or any(f["status"] != "uploaded" for f in files):
            raise HTTPException(409, "Finish uploading at least one file first.")
        db.execute("UPDATE files SET status='queued',stage='Queued' WHERE job_id=?", (job_id,))
        db.execute("UPDATE jobs SET state='submitted',updated_at=? WHERE id=?", (time.time(), job_id))
    return require_job(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str):
    require_job(job_id)
    with connect() as db:
        db.execute("UPDATE jobs SET cancel_requested=1,state='submitted' WHERE id=?", (job_id,))
    return {"ok": True}


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise HTTPException(404, "Job not found.")
        files = db.execute("SELECT * FROM files WHERE job_id=?", (job_id,)).fetchall()
        if any(f["status"] in {"processing", "uploading", "queued"} for f in files):
            raise HTTPException(409, "Cancel this job and wait for it to stop before deleting.")
        for file in files:
            remove_recording(file["id"])
            for ext in ("txt", "json", "txt.tmp", "json.tmp"):
                output_path(file["id"], ext).unlink(missing_ok=True)
        db.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def require_transcript(file_id, extension):
    with connect() as db:
        row = db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if row is None or not row["has_transcript"] or not output_path(file_id, extension).is_file():
        raise HTTPException(404, "Transcript is not available yet.")
    return dict(row)


@app.get("/api/files/{file_id}/download")
def download(file_id: str, format: Literal["txt", "json"] = "txt"):
    file = require_transcript(file_id, format)
    return FileResponse(
        output_path(file_id, format),
        filename=f"{Path(file['name']).stem}.{format}",
        media_type="text/plain; charset=utf-8" if format == "txt" else "application/json",
    )


@app.get("/api/files/{file_id}/preview")
def preview(file_id: str):
    require_transcript(file_id, "txt")
    with output_path(file_id, "txt").open(encoding="utf-8") as stream:
        content = stream.read(100001)
    return {"text": content[:100000], "truncated": len(content) > 100000}


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    job = require_job(job_id)
    available = [f for f in job["files"] if f["has_transcript"]]
    if not available:
        raise HTTPException(404, "No transcripts are available yet.")
    # Text output is small relative to media. Each file gets a unique prefix in the archive.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, file in enumerate(available, 1):
            for extension in ("txt", "json"):
                path = output_path(file["id"], extension)
                if path.is_file():
                    archive.write(path, f"{index:02d}-{Path(file['name']).stem}.{extension}")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="transcripts-{job_id[:8]}.zip"'},
    )


if settings.frontend.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend, html=True), name="frontend")
