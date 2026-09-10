"""One file per process: CPU models and audio memory are released on exit."""

import gc
import json
import os
import subprocess
import sys
import time

from .config import settings
from .db import connect, update_file
from .transcripts import save_result


class MediaError(Exception):
    """An actionable decoder error that is safe to display."""


class StageProgress:
    def __init__(self, file_id, stage):
        self.file_id = file_id
        self.started = time.monotonic()
        self.last_write = 0.0
        self.last_percent = 0.0
        update_file(file_id, stage=stage, stage_started_at=time.time(), progress=None, eta_seconds=None)

    def __call__(self, percent):
        percent = min(100.0, max(self.last_percent, float(percent)))
        now = time.monotonic()
        if now - self.last_write < 1 and percent < 100:
            return
        self.last_write = now
        self.last_percent = percent
        elapsed = now - self.started
        # Estimate this stage only. VAD, model loading and later stages have unknown costs.
        eta = elapsed * (100 - percent) / percent if 5 <= percent < 100 and elapsed >= 15 else None
        update_file(self.file_id, progress=percent, eta_seconds=eta)


def decode_audio(file_id):
    directory = settings.data / "recordings" / file_id
    source, wav = directory / "source", directory / "audio.wav"
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index:format=duration",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if probe.returncode:
        raise MediaError("This file could not be read as audio or video. Try another format.")
    metadata = json.loads(probe.stdout)
    if not metadata.get("streams"):
        raise MediaError("This file has no audio track.")
    duration = float(metadata.get("format", {}).get("duration", 0) or 0)
    if duration > settings.max_duration:
        raise MediaError(f"Recording exceeds the {settings.max_duration // 60}-minute duration limit.")
    # Decode to disk, with a hard duration cap even for misleading or missing metadata.
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-t",
            str(settings.max_duration + 1),
            "-threads",
            str(settings.threads),
            str(wav),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=1800,
        check=False,
    )
    if decoded.returncode:
        raise MediaError("Audio decoding failed. The recording may be incomplete or unsupported.")
    import wave

    with wave.open(str(wav)) as stream:
        duration = stream.getnframes() / stream.getframerate()
    if duration <= 0 or duration > settings.max_duration:
        raise MediaError("Recording is empty or exceeds the configured duration limit.")
    update_file(file_id, duration=duration)
    return wav


def run(file_id):
    with connect() as db:
        file = dict(db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone())
        job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (file["job_id"],)).fetchone())
    warnings = []
    try:
        wav = decode_audio(file_id)
        StageProgress(file_id, "Loading transcription model")
        import torch
        import whisperx

        torch.set_num_threads(settings.threads)
        audio = whisperx.load_audio(str(wav))
        model = whisperx.load_model(
            job["model"],
            "cpu",
            compute_type="int8",
            language="en",
            threads=settings.threads,
            vad_method="silero",
            download_root=str(settings.models / "whisper"),
        )
        progress = StageProgress(file_id, "Transcribing")
        result = model.transcribe(audio, batch_size=1, language="en", verbose=False, progress_callback=progress)
        del model
        gc.collect()
        # A checkpoint protects the transcript if alignment/diarization fails or is interrupted.
        save_result(
            file_id,
            result,
            file["name"],
            job["model"],
            ["Processing is incomplete; this is a transcription checkpoint."],
        )
        update_file(file_id, has_transcript=1)
        raw_segments = result["segments"]
        if raw_segments:
            align_model = None
            try:
                StageProgress(file_id, "Loading timestamp model")
                align_model, metadata = whisperx.load_align_model(
                    "en", "cpu", model_dir=str(settings.models / "alignment")
                )
                progress = StageProgress(file_id, "Aligning timestamps")
                result = whisperx.align(
                    raw_segments,
                    align_model,
                    metadata,
                    audio,
                    "cpu",
                    return_char_alignments=False,
                    progress_callback=progress,
                )
                result["language"] = "en"
                result["raw_segments"] = raw_segments
            except Exception:  # noqa: BLE001 - preserve ASR output when an optional model stage fails
                warnings.append("Word alignment failed. Original segment timestamps and text are preserved.")
            finally:
                del align_model
                gc.collect()
            save_result(
                file_id,
                result,
                file["name"],
                job["model"],
                warnings + ["Processing is incomplete; speaker labeling has not finished."],
            )
            if job["diarize"]:
                diarizer = None
                try:
                    from whisperx.diarize import DiarizationPipeline

                    StageProgress(file_id, "Loading speaker model")
                    diarizer = DiarizationPipeline(
                        token=settings.hf_token, device="cpu", cache_dir=str(settings.models / "huggingface")
                    )
                    progress = StageProgress(file_id, "Identifying speakers")
                    diarized = diarizer(audio, progress_callback=progress)
                    result = whisperx.assign_word_speakers(diarized, result)
                    result["speaker_turns"] = diarized[["start", "end", "speaker"]].to_dict("records")
                except Exception:  # noqa: BLE001 - speaker failure must not discard the transcript
                    warnings.append(
                        "Speaker labeling failed. Check HF_TOKEN and model access; transcript and timestamps are preserved."
                    )
                finally:
                    del diarizer
                    gc.collect()
            else:
                warnings.append("Speaker labeling was not enabled for this job.")
        StageProgress(file_id, "Saving transcript")
        save_result(file_id, result, file["name"], job["model"], warnings)
        update_file(
            file_id,
            status="completed",
            stage="Complete",
            progress=100,
            eta_seconds=None,
            warnings=json.dumps(warnings),
            finished_at=time.time(),
            has_transcript=1,
        )
    except Exception as error:  # noqa: BLE001 - process boundary; report a safe failure to the queue
        # Never put model-library exception text (which may contain tokens) in API responses/logs.
        message = str(error) if isinstance(error, MediaError) else None
        update_file(
            file_id,
            status="failed",
            stage="Failed",
            progress=None,
            eta_seconds=None,
            error=message
            or "Processing failed. Check model downloads, available memory and disk space. Upload again to retry.",
            finished_at=time.time(),
        )
        print(f"File {file_id} failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # Avoid telemetry from model libraries. No recording is sent to an external service.
    os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")
    sys.exit(run(sys.argv[1]))
