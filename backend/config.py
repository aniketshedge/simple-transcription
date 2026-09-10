import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data: Path = Path(os.getenv("DATA_DIR", "data"))
    models: Path = Path(os.getenv("MODEL_DIR", "models"))
    frontend: Path = Path(os.getenv("FRONTEND_DIR", "frontend/dist"))
    hf_token: str = os.getenv("HF_TOKEN", "")
    threads: int = max(1, int(os.getenv("CPU_THREADS", "3")))
    max_file_bytes: int = int(os.getenv("MAX_FILE_MB", "4096")) * 1024 * 1024
    max_files: int = int(os.getenv("MAX_FILES_PER_JOB", "20"))
    max_duration: int = int(os.getenv("MAX_DURATION_SECONDS", "10800"))
    upload_ttl: int = int(os.getenv("UPLOAD_TTL_HOURS", "24")) * 3600
    worker_enabled: bool = os.getenv("WORKER_ENABLED", "1") == "1"

    def prepare(self):
        for path in (self.data, self.models, self.data / "recordings", self.data / "transcripts"):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
