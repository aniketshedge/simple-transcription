from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend import app, config, db, engine, transcripts, worker


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = replace(
        config.settings,
        data=tmp_path / "data",
        models=tmp_path / "models",
        worker_enabled=False,
        hf_token="",
        max_file_bytes=1024,
        max_files=3,
    )
    for module in (app, config, db, engine, transcripts, worker):
        monkeypatch.setattr(module, "settings", settings)
    with TestClient(app.app) as test_client:
        yield test_client


@pytest.fixture
def new_job(client):
    def create(name="Interview", model="small", content=b"fake media", filename="recording.mp4", submit=True):
        result = client.post("/api/jobs", json={"name": name, "model": model})
        assert result.status_code == 201
        job = result.json()
        result = client.put(f"/api/jobs/{job['id']}/files", params={"filename": filename}, content=content)
        assert result.status_code == 201
        if submit:
            assert client.post(f"/api/jobs/{job['id']}/submit").status_code == 200
        return client.get(f"/api/jobs/{job['id']}").json()

    return create
