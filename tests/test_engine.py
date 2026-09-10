import sys
from types import SimpleNamespace

import pytest

from backend import db, engine, worker
from backend.transcripts import output_path, timestamp


def test_timestamp_rounding():
    assert timestamp(3599.9999) == "01:00:00.000"
    assert timestamp(None) == "unknown"


def test_progress_eta_is_per_stage(client, new_job, monkeypatch):
    file_id = new_job()["files"][0]["id"]
    now = [100.0]
    monkeypatch.setattr(engine.time, "monotonic", lambda: now[0])
    progress = engine.StageProgress(file_id, "Transcribing")
    progress(1)
    with db.connect() as connection:
        assert connection.execute("SELECT eta_seconds FROM files WHERE id=?", (file_id,)).fetchone()[0] is None
    now[0] = 120.0
    progress(25)
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        assert row["eta_seconds"] == 60
        assert row["progress"] == 25
    engine.StageProgress(file_id, "Aligning timestamps")
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        assert row["eta_seconds"] is None and row["progress"] is None


@pytest.mark.parametrize("alignment_fails", [False, True])
def test_engine_preserves_transcript_if_alignment_fails(client, new_job, monkeypatch, alignment_fails):
    job = new_job()
    file_id = job["files"][0]["id"]
    calls = {}
    raw = {"segments": [{"start": 0, "end": 1, "text": "Hello world."}], "language": "en"}

    def load_model(model, device, **kwargs):
        calls.update(model=model, device=device, **kwargs)
        return SimpleNamespace(transcribe=lambda *args, **kw: raw.copy())

    def align(*args, **kwargs):
        if alignment_fails:
            raise RuntimeError("Secret-token-must-not-appear")
        return {"segments": [{**raw["segments"][0], "words": [{"word": "Hello", "start": 0, "end": 0.5}]}]}

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=lambda _: None))
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        SimpleNamespace(
            load_audio=lambda _: [],
            load_model=load_model,
            load_align_model=lambda *args, **kwargs: (None, {}),
            align=align,
        ),
    )
    monkeypatch.setattr(engine, "decode_audio", lambda _: "audio.wav")
    assert engine.run(file_id) == 0
    result = client.get(f"/api/jobs/{job['id']}").json()["files"][0]
    assert result["status"] == "completed" and result["has_transcript"]
    assert calls["compute_type"] == "int8" and calls["device"] == "cpu" and calls["model"] == "small"
    text = output_path(file_id, "txt").read_text()
    assert "Hello world." in text and "Secret-token" not in text
    assert ("Word alignment failed" in text) == alignment_fails


def test_worker_unexpected_exit_cleans_recording(client, new_job, monkeypatch):
    job = new_job()
    file_id = job["files"][0]["id"]
    monkeypatch.setattr(worker.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(poll=lambda: 9))
    worker.Worker().tick()
    result = client.get(f"/api/jobs/{job['id']}").json()["files"][0]
    assert result["status"] == "failed"
    assert not (db.settings.data / "recordings" / file_id).exists()


def test_worker_launch_failure_does_not_leave_stuck_job(client, new_job, monkeypatch):
    job = new_job()
    file_id = job["files"][0]["id"]

    def fail(*args, **kwargs):
        raise OSError("Cannot create process")

    monkeypatch.setattr(worker.subprocess, "Popen", fail)
    worker.Worker().tick()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "failed"
    assert not (db.settings.data / "recordings" / file_id).exists()


def test_cancelling_queued_job_during_another_file(client, new_job, monkeypatch):
    first = new_job()
    queued = new_job()
    polls = iter([None, 0])

    def launch(*args, **kwargs):
        client.post(f"/api/jobs/{queued['id']}/cancel")
        return SimpleNamespace(poll=lambda: next(polls))

    runner = worker.Worker()
    monkeypatch.setattr(worker.subprocess, "Popen", launch)
    monkeypatch.setattr(runner.stop, "wait", lambda _: False)
    runner.tick()
    assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "cancelled"
    assert not (db.settings.data / "recordings" / queued["files"][0]["id"]).exists()
    assert client.get(f"/api/jobs/{first['id']}").json()["status"] == "failed"


def test_shutdown_stops_worker_and_requeues_recording(client, new_job, monkeypatch):
    job = new_job()
    runner = worker.Worker()

    def launch(*args, **kwargs):
        runner.stop.set()
        return SimpleNamespace(poll=lambda: None)

    stopped = []
    monkeypatch.setattr(worker.subprocess, "Popen", launch)
    monkeypatch.setattr(runner, "terminate", lambda process: stopped.append(True))
    runner.tick()
    assert stopped
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"
    assert (db.settings.data / "recordings" / job["files"][0]["id"] / "source").exists()


def test_decoder_rejects_invalid_media(client, new_job):
    import shutil

    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe is not installed")
    file_id = new_job()["files"][0]["id"]
    with pytest.raises(engine.MediaError, match="could not be read"):
        engine.decode_audio(file_id)
