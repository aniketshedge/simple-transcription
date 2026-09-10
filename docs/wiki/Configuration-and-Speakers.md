# Configuration and Speakers

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

Copy `.env.example` to the ignored, host-side `.env`. The current defaults are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HF_TOKEN` | empty | Optional access to the gated speaker model. |
| `BIND_ADDRESS` | `0.0.0.0` | Host interface published by Compose. |
| `PORT` | `8000` | Host port mapped to the container. |
| `CPU_THREADS` | `3` | PyTorch/CTranslate2 CPU threads. |
| `MAX_FILE_MB` | `4096` | Maximum uploaded bytes per file in MiB. |
| `MAX_FILES_PER_JOB` | `20` | Maximum files in one job. |
| `MAX_DURATION_SECONDS` | `10800` | Three-hour decoded-duration limit. |
| `UPLOAD_TTL_HOURS` | `24` | Abandoned upload expiry. |

CPU and memory container ceilings are configured separately in `compose.yaml`. Run one application container with one Uvicorn worker per data volume.

After changing `.env`, recreate the service with `docker compose up -d`. Run optional warmup while the queue is idle:

```sh
docker compose exec transcription python -m backend.warmup --model small
docker compose exec transcription python -m backend.warmup --model medium
docker compose exec transcription python -m backend.warmup --model both
docker compose exec transcription python -m backend.warmup --model small --speakers
```

The `--speakers` form requires `HF_TOKEN`. Warmup downloads weights; it does not upload or transcribe a recording. [Self-Hosting](https://github.com/aniketshedge/simple-transcription/wiki/Self-Hosting) covers the container and private-network setup.

## Enable speaker labels

Speaker labeling is optional. It needs one-time access to [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1). Accept that model’s terms with a Hugging Face account, then create a token under the same account. A fine-grained token with read access to that gated model is sufficient; the broader **Read access to contents of all public gated repos you can access** permission also works. A token with the **Read** role also works. Read access to your own repositories is not required by this app. No write, admin, Inference Providers, or hosted-endpoint permission is needed. See [Hugging Face token permissions](https://huggingface.co/docs/hub/en/security-tokens).

Set `HF_TOKEN=hf_...` only in the ignored server-side `.env` (replace the placeholder with your token), then recreate the container. The token does not itself grant access if the model terms were not accepted. No token is needed for ordinary transcription or timestamp alignment. Enable **Identify speakers** per job after the host setup. Labels such as `SPEAKER_00` are anonymous and local to one recording; they do not identify real people or match voices across files. A speaker-model or diarization failure saves text and timestamps with a warning.

For stage behavior and output formats, see [Processing and Output](https://github.com/aniketshedge/simple-transcription/wiki/Processing-and-Output).
