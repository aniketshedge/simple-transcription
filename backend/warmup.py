"""Download model weights without uploading or transcribing a recording."""

import argparse
import gc

from .config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["small", "medium", "both"], default="small")
    parser.add_argument("--speakers", action="store_true")
    args = parser.parse_args()
    settings.prepare()
    if args.speakers and not settings.hf_token:
        parser.error("Set HF_TOKEN and accept the speaker model terms before using --speakers.")
    import torch
    import whisperx

    torch.set_num_threads(settings.threads)
    for size in ["small", "medium"] if args.model == "both" else [args.model]:
        print(f"Downloading {size} transcription and voice detection models…", flush=True)
        model = whisperx.load_model(
            size,
            "cpu",
            compute_type="int8",
            language="en",
            vad_method="silero",
            threads=settings.threads,
            download_root=str(settings.models / "whisper"),
        )
        del model
        gc.collect()
    print("Downloading English timestamp model…", flush=True)
    model, _ = whisperx.load_align_model("en", "cpu", model_dir=str(settings.models / "alignment"))
    del model
    gc.collect()
    if args.speakers:
        from whisperx.diarize import DiarizationPipeline

        print("Downloading speaker model…", flush=True)
        model = DiarizationPipeline(
            token=settings.hf_token, device="cpu", cache_dir=str(settings.models / "huggingface")
        )
        del model
    print("Models are cached and ready.", flush=True)


if __name__ == "__main__":
    main()
