# User Troubleshooting

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

Use the symptom below as the next step. Ask the host for server-side or token issues; do not post recordings, transcripts, tokens, or private addresses in a public issue. When requesting help, share the job status and visible warning text instead.

| Symptom | Next step |
| --- | --- |
| Cannot connect | Check Tailscale, then home Wi-Fi for a local address, and ask the host whether the NUC and app are running. See [Mobile and Connectivity](https://github.com/aniketshedge/simple-transcription/wiki/Mobile-and-Connectivity). |
| Upload interrupted | Keep the phone awake and the app open until the job enters the queue. Cancel the incomplete job and upload your own source file again. |
| Model loading is waiting | The first use may download model weights. Ask the host to check internet access, disk space, logs, and cached models. |
| ETA changes or disappears | ETA covers the current stage only. Model loading and uneven speaker steps may have no percentage; later stages and queued files are not included. |
| Unsupported file or no audio track | Try another copy or format. The server checks the actual media with FFmpeg, and a video must contain an audio track. |
| Speaker labels are missing | The host must configure `HF_TOKEN` and model access, and the job must enable speaker labeling. A failure preserves text with a warning. |
| Partial transcript | Download it if useful and read the warning. If still processing, wait for later stages; if failed or cancelled, re-upload your source to retry. A checkpoint is not proof that the job is complete. |
| Words are inaccurate | Try clearer audio, the Small or Medium model as appropriate, and inspect timestamps. Automatic transcription and speaker assignments can be wrong. |
| Job failed | Read the visible error. Ask the host to check model access, RAM, disk space, and logs; re-upload the original file to retry. |

Recordings are temporary and the server normally removes them after success, failure, or cancellation. Preserve your own source copy until you are satisfied with the transcript. For output details, see [Processing and Output](https://github.com/aniketshedge/simple-transcription/wiki/Processing-and-Output).
