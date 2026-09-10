# Validation — 10 September 2026

Validated locally with Docker 29.7.2 on an Apple Silicon Mac, running the NUC's `linux/amd64` image under emulation. The container used Python 3.12, WhisperX 3.8.6, PyTorch 2.8.0+cpu (`CUDA: None`), and non-root UID 10001.

## Checks that passed

- Vue/TypeScript production build and Python lint checks.
- 21 automated tests covering uploads, limits, safe filenames, same-origin writes, queue ordering, restart recovery, transcript downloads, partial results, model-stage failures, and cancellation.
- Browser checks of the empty state, job creation, model selection, multi-file upload, history, and transcript preview at a 390-pixel phone viewport and the desktop viewport.
- A synthetic English speech recording of approximately six seconds, uploaded through the browser as both WAV audio and MP4 video, completed using the **small** model.
- The same speech recording completed using the **medium** model.
- TXT and JSON downloads contained the expected recognized text and aligned word timestamps; ZIP downloads contained both formats for each uploaded file.
- The two completed jobs and model caches survived replacement of the container with the final image.
- Invalid media failed with an actionable error.
- Cancelling a queued job completed while another file was still processing. Cancelling the active job then stopped its worker.
- The recording directory was empty after successful, failed, and cancelled processing; transcript files remained.
- Final container health check passed. Installer caches were excluded from the runtime model volume.

## Not measured or verified

- **N100 throughput and peak memory for long recordings.** These were short functional checks under emulation, not a hardware benchmark or a two-hour stress test.
- **Live diarization.** No Hugging Face token/model access was supplied. Speaker labeling is implemented against the pinned WhisperX API and requires the README's one-time setup.
- Physical NUC deployment and LAN/Tailscale routing; the test instance was bound to localhost on port 8001.

The test instance keeps only the completed synthetic transcripts as examples. Temporary source media and the failed/cancelled test jobs were removed.

## Segment-only TXT follow-up

- Updated TXT generation to retain segment text, start/end timestamps, and speaker labels while omitting word timings and confidence scores. Existing saved TXT files retain their previous format.
- All 21 backend tests and Python lint checks pass. Download coverage verifies concise TXT output in individual downloads, previews, and ZIP archives, and confirms that JSON retains the full model results.
- Documented Hugging Face read-only token permissions and gated-model access setup. Live token/model access remains unverified without credentials.

## PWA follow-up

- Added manifest, standalone display configuration, normal/maskable PNG icons, an Apple touch icon, and home-screen installation guidance.
- Seven service-worker tests passed, including network failure, server errors, timeouts, cache upgrades, icon dimensions, and exclusion of all API/download routes from offline caching. The 21 backend tests also still pass.
- The browser parsed the deployed manifest without errors.
- Stopping the Docker container triggered the Tailscale connection prompt in an already-open app. Reloading with the container still stopped loaded the cached offline page successfully.
- Retrying while disconnected displayed a useful failure message. Starting the container and selecting Try again returned to the existing job history.
- No real phone installation or Tailscale VPN toggle was performed. HTTPS setup and platform-specific installation must be completed on the actual phone/NUC. Localhost is treated as a secure origin for these desktop tests.
