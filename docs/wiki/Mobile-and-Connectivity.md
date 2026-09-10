# Mobile and Connectivity

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

## Install on a phone

Simple Transcription can be installed as a PWA. On Android, use your browser’s **Install app** or **Add to Home screen** option. On iPhone or iPad, open the app in Safari, tap **Share**, then **Add to Home Screen**. The in-app installation guidance explains the same steps.

HTTPS is needed for phone service workers and the offline connection page. An ordinary LAN address such as `http://192.168.…` or a Tailscale-IP address such as `http://100.…` does not provide that support, even when the device is otherwise connected through Tailscale. The regular site can still work over HTTP. For host-side HTTPS, see [Self-Hosting](https://github.com/aniketshedge/simple-transcription/wiki/Self-Hosting).

Visit the app successfully once over HTTPS while connected so its offline assets can be saved. If a later connection fails, the cached page offers a **Try again** button and a reminder to check Tailscale. A first-ever disconnected visit, cleared site data, browser storage eviction, certificate errors, or unsupported service workers cannot rely on that fallback.

## Reconnect

Check Tailscale first, then Wi-Fi if you use a local address, and finally whether the host and Simple Transcription container are running. The browser cannot inspect VPN state, so the app cannot prove that Tailscale is disconnected. An already-open app keeps the current form in memory and shows the same guidance when an API request fails.

Only the offline page, manifest, and icons are cached. The service worker does not cache API responses, recordings, transcripts, previews, downloads, or job data, and it does not provide an offline upload queue. GitHub Wiki help itself requires internet access; essential reconnect instructions remain inside the app. Keep the app open and the phone awake until uploads finish.

For common connection symptoms, see [User Troubleshooting](https://github.com/aniketshedge/simple-transcription/wiki/User-Troubleshooting).
