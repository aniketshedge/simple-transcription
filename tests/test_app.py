import io
import time
import zipfile

import pytest

from backend import db, worker
from backend.transcripts import save_result


def test_multiple_files_queue_and_model_validation(client, new_job):
    job = new_job(model="medium", submit=False)
    assert (
        client.put(f"/api/jobs/{job['id']}/files", params={"filename": "voice.m4a"}, content=b"audio").status_code
        == 201
    )
    result = client.post(f"/api/jobs/{job['id']}/submit").json()
    assert result["model"] == "medium"
    assert result["status"] == "queued"
    assert len(result["files"]) == 2
    assert client.post(f"/api/jobs/{job['id']}/submit").status_code == 200
    assert client.post("/api/jobs", json={"name": "Invalid", "model": "tiny"}).status_code == 422
    assert client.post("/api/jobs", json={"name": "   "}).status_code == 422
    assert client.post("/api/jobs", json={"name": "Speakers", "diarize": True}).status_code == 422


def test_no_empty_or_incomplete_submission(client):
    job = client.post("/api/jobs", json={"name": "Empty"}).json()
    assert client.post(f"/api/jobs/{job['id']}/submit").status_code == 409
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO files(id,job_id,name,created_at) VALUES ('uploading',?,'file',?)", (job["id"], time.time())
        )
    assert client.post(f"/api/jobs/{job['id']}/submit").status_code == 409


@pytest.mark.parametrize("content,status", [(b"", 422), (b"x" * 1025, 413)])
def test_upload_limits_clean_up(client, content, status):
    job = client.post("/api/jobs", json={"name": "Upload"}).json()
    result = client.put(f"/api/jobs/{job['id']}/files", params={"filename": "a.mp3"}, content=content)
    assert result.status_code == status
    assert client.get(f"/api/jobs/{job['id']}").json()["files"] == []
    assert list(db.settings.data.joinpath("recordings").iterdir()) == []


def test_streaming_upload_without_content_length_limit(client):
    job = client.post("/api/jobs", json={"name": "Streaming"}).json()
    result = client.put(
        f"/api/jobs/{job['id']}/files", params={"filename": "a.mp3"}, content=iter([b"x" * 700, b"x" * 700])
    )
    assert result.status_code == 413
    assert client.get(f"/api/jobs/{job['id']}").json()["files"] == []


def test_filenames_are_not_storage_paths(client, new_job):
    job = new_job(filename="../../outside\r\n.mp3")
    file = job["files"][0]
    assert file["name"] == "outside.mp3"
    assert (db.settings.data / "recordings" / file["id"] / "source").read_bytes() == b"fake media"
    assert client.get("/api/files/unknown/download").status_code == 404
    assert client.get(f"/api/files/{file['id']}/download?format=exe").status_code == 422


def test_cross_origin_writes_blocked(client):
    assert (
        client.post("/api/jobs", json={"name": "Attack"}, headers={"origin": "https://evil.example"}).status_code == 403
    )
    assert client.post("/api/jobs", json={"name": "Local"}, headers={"origin": "http://testserver"}).status_code == 201
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"


def test_cancel_queued_removes_recording_and_delete_is_guarded(client, new_job):
    job = new_job()
    file = job["files"][0]
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 409
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
    worker.Worker().tick()
    assert not (db.settings.data / "recordings" / file["id"]).exists()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "cancelled"
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_downloads_use_segment_text_preserve_json_and_duplicate_names(client, new_job):
    job = new_job(submit=False)
    client.put(f"/api/jobs/{job['id']}/files", params={"filename": "recording.mp4"}, content=b"audio")
    job = client.post(f"/api/jobs/{job['id']}/submit").json()
    result = {
        "segments": [
            {
                "start": 0.1,
                "end": 1.0,
                "text": "Hello",
                "speaker": "SPEAKER_00",
                "words": [{"start": 0.2, "end": 0.9, "word": "Hello", "score": 0.95, "speaker": "SPEAKER_00"}],
            }
        ]
    }
    for file in job["files"]:
        save_result(file["id"], result, file["name"], "small", [])
        db.update_file(file["id"], has_transcript=1, status="completed")
    text = client.get(f"/api/files/{file['id']}/download").text
    assert "[00:00:00.100 --> 00:00:01.000] SPEAKER_00: Hello" in text
    assert "score=" not in text
    assert "00:00:00.200" not in text and "00:00:00.900" not in text
    assert text.count("Hello") == 1
    assert client.get(f"/api/files/{file['id']}/download?format=json").json()["result"] == result
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{job['id']}/download").content))
    assert len(archive.namelist()) == len(set(archive.namelist())) == 4
    for name in archive.namelist():
        if name.endswith(".txt"):
            assert archive.read(name).decode("utf-8") == text
    assert client.get(f"/api/files/{file['id']}/preview").json()["text"] == text
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert not list((db.settings.data / "transcripts").iterdir())


def test_recovery_retains_queued_audio_removes_terminal_and_partial_uploads(client, new_job):
    queued = new_job()
    completed = new_job()
    interrupted = new_job(submit=False)
    db.update_file(queued["files"][0]["id"], status="processing")
    db.update_file(completed["files"][0]["id"], status="completed")
    db.update_file(interrupted["files"][0]["id"], status="uploading")
    worker.recover()
    assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "queued"
    assert (db.settings.data / "recordings" / queued["files"][0]["id"] / "source").exists()
    assert not (db.settings.data / "recordings" / completed["files"][0]["id"]).exists()
    assert client.get(f"/api/jobs/{interrupted['id']}").json()["files"] == []


def test_abandoned_uploads_expire(client, new_job):
    job = new_job(submit=False)
    with db.connect() as connection:
        connection.execute("UPDATE jobs SET updated_at=0 WHERE id=?", (job["id"],))
    worker.cleanup_abandoned()
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert not list((db.settings.data / "recordings").iterdir())


def test_queue_fifo_and_partial_status(client, new_job):
    first = new_job()
    second = new_job()
    assert db.claim_file()["job_id"] == first["id"]
    assert db.claim_file()["job_id"] == second["id"]
    assert db.claim_file() is None
    db.update_file(first["files"][0]["id"], status="failed", has_transcript=1)
    assert client.get(f"/api/jobs/{first['id']}").json()["status"] == "partial"
