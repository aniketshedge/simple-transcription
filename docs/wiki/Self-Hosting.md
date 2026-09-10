# Self-Hosting

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

Simple Transcription is designed for a Linux x86-64 machine such as an Intel N100 NUC with 16 GB RAM. Docker Engine with Compose v2 is required. FFmpeg, WhisperX, and the CPU ML stack are bundled into one `linux/amd64` image. The default deployment uses English, CPU INT8 inference, one worker, batch size one, and one file at a time.

## Deploy

On the host, run:

```sh
git clone https://github.com/aniketshedge/simple-transcription.git
cd simple-transcription
cp .env.example .env
docker compose up -d
```

Open `http://<nuc-lan-ip>:8000` or `http://<nuc-tailscale-ip>:8000` on a trusted device. The first image build downloads Python/ML dependencies, and the first job using a model may download its weights. Named volumes persist the job database, upload/recording storage, transcripts, and model cache through image updates and container replacement. Incomplete HTTP uploads are discarded during restart recovery. See [Maintenance and Troubleshooting](https://github.com/aniketshedge/simple-transcription/wiki/Maintenance-and-Troubleshooting) for updates and recovery.

The Compose file uses `pull_policy: build`, so `git pull && docker compose up -d` rebuilds with new source code. The default container ceiling is three CPUs and 10 GB RAM, with three CPU threads and batch size one. These are defaults for a small NUC, not measured throughput guarantees; test your own recordings and leave disk space for queued uploads, decoded audio, and models. See [Configuration and Speakers](https://github.com/aniketshedge/simple-transcription/wiki/Configuration-and-Speakers).

## Private access and HTTPS

There is no authentication. Anyone who can reach the published port can view, upload, cancel, download, and delete jobs. Keep the service on a trusted LAN or Tailscale network. Do not use router port forwarding or public ingress. Set `BIND_ADDRESS` in `.env` to restrict the host interface when appropriate; the default publishes on all host interfaces.

For private HTTPS through Tailscale Serve, with Tailscale installed and connected on the NUC, run:

```sh
sudo tailscale serve --bg http://127.0.0.1:8000
```

Follow Tailscale’s HTTPS setup prompt and open the private `https://<nuc>.<tailnet>.ts.net` address on a phone connected to Tailscale. Keep Funnel disabled. For Serve-only access, set `BIND_ADDRESS=127.0.0.1` in `.env` and run `docker compose up -d` to apply it. For LAN plus Serve access, use `BIND_ADDRESS=0.0.0.0`. The command above assumes `PORT=8000`; if you change the published port, update the Serve target too. A bind restricted to a different host IP will not be reachable through `127.0.0.1`. See the [Tailscale Serve documentation](https://tailscale.com/docs/features/tailscale-serve). See [Mobile and Connectivity](https://github.com/aniketshedge/simple-transcription/wiki/Mobile-and-Connectivity) for PWA requirements.
