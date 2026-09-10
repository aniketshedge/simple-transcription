# Simple Transcription

A small, mobile-first Vue application for turning audio and video into English transcripts on your own server. No user accounts, cloud transcription API, or external database.

- Named jobs with multiple recordings, persistent history, a sequential queue, and cancellation.
- WhisperX **small** or **medium**, selected per job, using CPU INT8 inference.
- Segment text with start/end timestamps and optional speaker labels in TXT output.
- A UTF-8 `.txt` per recording, a structured `.json` companion, and ZIP downloads for a job.
- Upload progress, live processing stages, and an approximate **current-stage** ETA.
- Recordings automatically removed after completion, failure, or cancellation. Transcripts remain until you delete the job.

## Deploy on the NUC

Requires a Linux x86-64 machine and current Docker Engine with Docker Compose v2. This configuration targets an Intel N100 with 16 GB RAM. Install Docker and clone this repository onto the NUC, then run:

```sh
cp .env.example .env
docker compose up -d
```

Open `http://<nuc-lan-ip>:8000` or `http://<nuc-tailscale-ip>:8000` from your phone or computer. Tailscale runs on the host; it is not bundled into this container.

For subsequent updates:

```sh
git pull && docker compose up -d
```

The Compose `pull_policy: build` setting rebuilds the image on `up`, so new source code is picked up automatically. Cached dependency layers keep routine updates quicker. Using `&&` prevents an update after a failed pull. Without `-d`, Compose stays attached to logs; use `-d` for SSH deployments so the app keeps running after you disconnect.

```sh
docker compose logs -f --tail=100
docker compose ps
docker compose down
```

Named volumes preserve the job database, in-progress uploads, transcripts, and model cache through image updates and container replacement. **Do not use `docker compose down -v` unless you intend to erase all jobs and cached models.**

The first build downloads Python/ML dependencies. The first job with a model downloads its weights. Model downloads need internet access; your recordings are processed locally and never uploaded to a transcription service. Model libraries may check for cache updates on later runs. Their telemetry is disabled in the container.

Optionally prepare all model weights before submitting jobs (do this while the queue is idle):

```sh
docker compose exec transcription python -m backend.warmup --model both
```

## Install on your phone (PWA)

Simple Transcription includes a web app manifest, home-screen icons, and a service worker that saves a small offline connection page. An **Add to home screen** control opens the browser's install prompt when available, or shows platform instructions. On iPhone/iPad use Safari → Share → Add to Home Screen; on Android use the browser's Install app / Add to Home screen option.

**Use HTTPS on the phone.** Plain `http://192.168.…` or `http://100.…` addresses do not support service workers, even over an encrypted Tailscale connection. HTTP localhost works for testing on the same computer only. The regular website still works over HTTP, but the installable/offline experience needs a secure origin.

For private HTTPS access, run this on the NUC with Tailscale installed and connected:

```sh
sudo tailscale serve --bg http://127.0.0.1:8000
```

Follow Tailscale's HTTPS setup prompt if needed, then open the `https://<nuc>.<tailnet>.ts.net` address it prints **on your phone while Tailscale is connected**. Install from that address. Tailscale Serve is private to your tailnet; do not enable Funnel for this application. The `--bg` setting persists across host restarts. This command assumes that the app uses the default port and the NUC's localhost can reach it; if `BIND_ADDRESS` was restricted to another IP, change it to `127.0.0.1` for Serve-only access or `0.0.0.0` for LAN plus Serve access.

When a previously visited app cannot reach the server, the saved page asks **“Are you connected to Tailscale?”** and offers **Try again**. It also suggests home Wi-Fi for local addresses and checking whether the NUC/app is running. Returning from the Tailscale app or a browser connectivity event retries the health check. An already-open app displays the same guidance when API calls fail or time out, preserving the current form in memory.

The browser cannot inspect the phone's VPN state, so it cannot prove that Tailscale is disconnected. A first-ever visit while disconnected cannot show the custom page: visit successfully once, allow the offline page to save, and retain browser storage. Clearing site data or browser cache eviction removes that fallback. Certificate errors and disabled service-worker support may still show browser errors.

Only the connection page, manifest, and icons are saved by the service worker. It does not cache job data, transcripts, uploads, or API responses, and it does not queue offline uploads. Server navigation uses the latest online app; offline assets are versioned per build. Installing the app does not let uploads continue reliably after iOS/Android suspends it—keep it open until uploads finish.

See [MDN's installability requirements](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable) and [Tailscale Serve documentation](https://tailscale.com/docs/features/tailscale-serve).

## Speaker labels

Speaker labeling is an additional local WhisperX/pyannote stage. It needs one-time access to a gated Hugging Face model:

1. Accept the terms at [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1).
2. Create a [Hugging Face token](https://huggingface.co/settings/tokens) under the **same account** that accepted the model terms. A token with the **Read** role is sufficient. For tighter scope, use a **fine-grained** token with read access to `pyannote/speaker-diarization-community-1`; ensure gated-model downloads are permitted. If using the broader gated-repository permission, enable **Read access to contents of all public gated repos you can access**.
3. Set `HF_TOKEN=...` in your local `.env` and run `docker compose up -d`.
4. Optionally cache it using `docker compose exec transcription python -m backend.warmup --model small --speakers`.

Only model download/read access is needed: no write, repository administration, or Inference Providers/Endpoints permissions. The token does not bypass the model's access terms. Keep it only in the ignored server-side `.env`; recordings and inference stay on your NUC. See [Hugging Face's token permissions documentation](https://huggingface.co/docs/hub/en/security-tokens).

The new-job screen enables speaker labeling by default when a token is configured. You can turn it off per job to save processing time. A configured token does not guarantee model access; if loading or diarization fails, the transcript is saved with a visible warning. Without a token, transcription and timestamps still work.

Labels such as `SPEAKER_00` distinguish voices within one recording; they do not identify real people or match speakers across files. Overlapping speech and speaker assignments may be inaccurate. No speaker embeddings are retained.

## Models, memory, and long recordings

| Model | Use it for | Tradeoff |
| --- | --- | --- |
| **Small** (default) | General recordings and shorter turnaround | Less accurate on difficult audio |
| **Medium** | Recordings where extra accuracy matters | Significantly more CPU work; benchmark on your own recordings |

Both are larger than Whisper's tiny and base models. Small is the recommended starting point for the N100. The default is three CPU threads, batch size one, one file at a time, a three-CPU container limit, and a 10 GB memory ceiling. Model stages release their references between transcription, alignment, and diarization; the process exits after each recording to return all its memory. Medium plus diarization on long recordings still needs real-world validation on your NUC; RAM capacity alone does not guarantee a fast transcription.

Audio and video formats understood by FFmpeg are accepted, including MP3, M4A, WAV, FLAC, OGG, MP4, MOV, MKV, and WebM. The **first audio track** is converted to 16 kHz mono; silent videos with no audio track produce a clear error. Defaults allow 20 files per job, 4 GB per file, and three hours per recording, covering the intended sub-two-hour recordings. Actual content is checked by FFmpeg, not just the filename.

Temporary disk space is required while files wait or process. Uploads stream directly to disk. A two-hour recording needs roughly 230 MB for the decoded mono WAV, in addition to the original and model caches. WhisperX also loads decoded audio into memory. Keep several GB free for models and the queue; do not submit more recordings than the NUC has space for.

On a normal restart, the current file starts over and queued files remain queued. Finished transcripts are retained. There is no mid-file inference resume. Completed, failed, and cancelled recordings are removed, including decoded copies. Partial HTTP uploads are discarded at restart; abandoned unsubmitted jobs expire after 24 hours. Incomplete uploads can be cancelled from history. Failed files require re-uploading because originals are not retained. File deletion is normal filesystem deletion, not secure erasure of underlying storage or backups.

## Progress and ETA

- **Upload:** measured bytes sent, across all selected files. Keep the browser open and the phone awake until the job enters the queue.
- **Queue:** completed-file count; jobs run FIFO, one file at a time.
- **Processing:** model loading, transcription, timestamp alignment, speaker labeling, and saving.
- **Stage percentage:** reported by WhisperX callbacks when available. Percentages restart at each stage and are not a percentage of total job time. Some work, including voice detection and clustering, may temporarily show no movement.
- **ETA:** a rough extrapolation within the current stage after at least 15 seconds and 5% progress. It excludes later stages, queued files, and model download time. Speaker-label stages contain uneven substeps, so this estimate can move substantially.

Closing the browser after uploading does not stop a queued job. Reopen its detail page to see progress. Polling pauses while the browser page is hidden.

## Output

Each `.txt` contains source/model metadata and segment text with start/end timestamps and speaker labels where available. Word-level timestamps and confidence scores are omitted. Missing timings are marked `unknown`; values are not fabricated. This compact format is suited to downstream LLM inputs.

```text
[00:00:03.240 --> 00:00:04.100] SPEAKER_00: Hello there.
```

The JSON companion preserves the full aligned results (including word timings and confidence scores where available), original ASR segments, and speaker turns. ZIP entries have numeric prefixes so files with the same name do not overwrite each other. The preview is capped at 100,000 characters; downloads contain the full text. Previously generated TXT files keep their saved format.

Transcripts are checkpointed after recognition and alignment. If a later stage fails, available text remains downloadable. Partial checkpoints explicitly say processing is incomplete. Alignment or speaker failures produce warnings rather than throwing away usable transcription.

## Configuration and private access

| `.env` variable | Default | Purpose |
| --- | --- | --- |
| `HF_TOKEN` | empty | Optional speaker model access |
| `BIND_ADDRESS` | `0.0.0.0` | Published interface; use a LAN/Tailscale IP to restrict it |
| `PORT` | `8000` | Host port |
| `CPU_THREADS` | `3` | PyTorch/CTranslate2 CPU threads |
| `MAX_FILE_MB` | `4096` | Maximum uploaded bytes per file in MiB |
| `MAX_FILES_PER_JOB` | `20` | Files per job |
| `MAX_DURATION_SECONDS` | `10800` | Hard decoded duration limit |
| `UPLOAD_TTL_HOURS` | `24` | Abandoned upload expiry |

Change CPU/memory container ceilings in `compose.yaml` separately if needed. Run **one application container with one Uvicorn worker** per data volume: its background supervisor owns the queue. Do not scale replicas or enable multiple Uvicorn workers against the same volume.

There are deliberately no accounts. Anyone who can reach this port can upload, read, cancel, download, and delete jobs. Keep it on a trusted LAN or Tailscale, with no router port forwarding or public ingress. By default Docker publishes on all host interfaces; set `BIND_ADDRESS` for a specific interface and apply appropriate host/Tailscale access rules. Cross-origin browser writes are rejected, but that is not authentication. When using a reverse proxy, preserve the original `Host` header and allow sufficient upload size/time.

The container runs as a non-root user, drops Linux capabilities, and uses a persistent model cache. `.env`, recordings, transcripts, databases, and caches are excluded from Git and Docker build context. The existing MIT license applies to this application's code; WhisperX, model weights, and dependencies retain their own licenses and model terms.

## Development and tests

Python 3.12–3.13, Node.js 22+, [uv](https://docs.astral.sh/uv/), and FFmpeg/ffprobe are required. Dependencies are locked in `uv.lock` and `frontend/package-lock.json`; Linux resolves CPU-only PyTorch wheels.

```sh
uv sync
uv run pytest -q
uv run ruff check backend tests
cd frontend
npm ci
npm test
npm run build
```

Run the API from the repository root and the Vue development server in a second terminal:

```sh
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

```sh
cd frontend
npm run dev
```

The Vite server proxies `/api` to FastAPI. Local development stores runtime data in ignored `data/` and `models/` directories. Set `WORKER_ENABLED=0` for UI/API-only development without loading models. That mode does not process or clean up queued jobs. Automated tests use temporary storage and mocked ML outputs; they cover lifecycle, validation, cancellation, restart recovery, downloads, and failure handling without model downloads.

For the deployment equivalent, run `docker compose build` and `docker compose up -d`. The container health check verifies API/database availability. Apple Silicon Macs run the NUC's `linux/amd64` image under emulation; timing there is not an N100 performance benchmark.

See [validation notes](docs/validation.md) for the completed Docker/browser checks and their limits.

## Upstream references

- [WhisperX usage, CPU INT8 configuration, alignment and diarization](https://github.com/m-bain/whisperX)
- [WhisperX 3.8.6](https://pypi.org/project/whisperx/3.8.6/)
- [faster-whisper CPU benchmarks](https://github.com/SYSTRAN/faster-whisper#small-model-on-cpu) (different CPU; do not assume the same timings on the N100)
