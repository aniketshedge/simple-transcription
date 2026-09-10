import json
import math
import os
from pathlib import Path

from .config import settings


def output_path(file_id: str, extension: str) -> Path:
    return settings.data / "transcripts" / f"{file_id}.{extension}"


def timestamp(seconds):
    if seconds is None or not math.isfinite(float(seconds)):
        return "unknown"
    milliseconds = round(max(0, seconds) * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{milliseconds:03}"


def render_text(result, name, model, warnings):
    lines = [
        "Simple Transcription",
        f"Source: {name}",
        f"Model: WhisperX / {model} / English",
        "Times are relative to the start of the recording.",
        "Speaker IDs are automatic, local to this file, and may be inaccurate.",
    ]
    lines.extend(f"Note: {warning}" for warning in warnings)
    lines.append("")
    for segment in result.get("segments", []):
        speaker = segment.get("speaker")
        label = f" {speaker}:" if speaker else ""
        lines.append(
            f"[{timestamp(segment.get('start'))} --> {timestamp(segment.get('end'))}]{label} {segment.get('text', '').strip()}"
        )
        # Keep word timings, confidence and speaker changes in the same LLM-ready text file.
        for word in segment.get("words", []):
            details = [f"{timestamp(word.get('start'))} --> {timestamp(word.get('end'))}"]
            if word.get("speaker"):
                details.append(str(word["speaker"]))
            if word.get("score") is not None:
                details.append(f"score={word['score']:.3f}")
            lines.append(f"  [{'; '.join(details)}] {word.get('word', '')}")
        lines.append("")
    if not result.get("segments"):
        lines.append("[No speech detected]")
    return "\n".join(lines) + "\n"


def atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def save_result(file_id, result, name, model, warnings):
    payload = {"source": name, "model": model, "language": "en", "warnings": warnings, "result": result}
    atomic_write(
        output_path(file_id, "json"),
        json.dumps(payload, ensure_ascii=False, indent=2, default=lambda value: value.item()),
    )
    atomic_write(output_path(file_id, "txt"), render_text(result, name, model, warnings))
