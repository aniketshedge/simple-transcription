# Maintenance and Troubleshooting

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

## Updates and operations

From the clone directory, update with:

```sh
git pull && docker compose up -d
```

Compose rebuilds the application image on `up`; cached dependency layers make routine updates quicker. Check health and logs with:

```sh
docker compose ps
docker compose logs -f --tail=100
```

Use `docker compose stop` and `docker compose start` for a temporary pause, or `docker compose down` to remove the container and network while keeping named-volume data. Cached weights, the database, fully uploaded queued recordings, and transcripts survive ordinary container replacement. Incomplete HTTP uploads are discarded during restart recovery. Do not use `docker compose down -v` unless you intend to erase all jobs and cached models.

## Backups and deletion

For a consistent snapshot, stop this app first and back up the Compose-managed `app-data` volume (the actual Docker volume name may include the Compose project prefix) and the ignored host `.env` or deployment configuration securely. The data volume can include queued recordings as well as transcripts; choose a backup retention policy that reflects this. Restart the app with `docker compose start` once the snapshot is complete. The `model-cache` volume is optional: weights can be downloaded again if access is available. Restore commands depend on your snapshot method and volume names; test a restore before relying on it. There are no automatic backups or secure-erasure guarantees. `down -v` and job deletion are destructive, and normal file deletion does not erase underlying storage or existing backups.

## Recovery and common host problems

- On restart, queued files remain queued and an interrupted file starts again from the beginning. An incomplete HTTP upload is discarded. Finished transcripts remain.
- Low disk space can block uploads or decoding. Keep room for original recordings, decoded audio, queued work, and model caches.
- Slow CPU or memory pressure can make a job take a long time or fail. Try Small, reduce concurrent host workloads, and inspect `docker compose logs`; do not scale replicas or add Uvicorn workers against the same data volume.
- A Hugging Face 401/403 usually means the token’s account did not accept the gated model terms or lacks read access. Review [Configuration and Speakers](https://github.com/aniketshedge/simple-transcription/wiki/Configuration-and-Speakers); never paste the token into logs or issues.
- A reverse proxy must preserve the original `Host` header and allow sufficient upload size and time. For phone offline fallback, use HTTPS and follow [Mobile and Connectivity](https://github.com/aniketshedge/simple-transcription/wiki/Mobile-and-Connectivity).

The repository’s [validation notes](https://github.com/aniketshedge/simple-transcription/blob/main/docs/validation.md) describe what has been tested and what has not. They do not establish N100 long-recording throughput or live diarization performance.
