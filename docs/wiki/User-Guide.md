# User Guide

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

## Start a transcription

1. Open the app address supplied by the person who hosts it. Connect your phone or computer to the required LAN or Tailscale network first. There is no account to create.
2. Create a named job and choose **Small** or **Medium**. Small is the quicker default; Medium uses substantially more CPU time and may help with difficult audio. Both are English-only, and neither promises a fixed runtime or perfect accuracy.
3. Select one or more audio or video files. You can optionally enable **Identify speakers** when the host has completed the speaker-model setup. See [Models and speakers](#models-and-speakers) below for help choosing.
4. Upload and follow the job in transcription history.

Keep the app open and the phone awake until all uploads finish. Once the files have been submitted to the queue, processing continues on the server if you close the browser. The history page can be reopened later.

## Models and speakers

Use **Small** for a shorter wait or **Medium** when extra accuracy matters enough to spend more CPU time. Both run locally. **Identify speakers** adds anonymous labels such as `SPEAKER_00`; it takes extra time and does not identify real people or match voices across recordings. If this option is unavailable, ask your host to enable it. See [Processing and Output](https://github.com/aniketshedge/simple-transcription/wiki/Processing-and-Output) for an example.

## Read and download results

For each recording, you can preview the transcript or download a `.txt` file. The optional `.json` download contains the structured result, and **Download all** creates a ZIP with both formats for the job. A partial transcript or warning can still be useful; see [Processing and Output](https://github.com/aniketshedge/simple-transcription/wiki/Processing-and-Output).

**Cancel** stops unfinished work and removes its recordings. Any transcript already checkpointed remains. **Delete** removes the job and its transcripts once the job is no longer active. The server removes source recordings and decoded audio after success, failure, or cancellation, while transcripts stay until you delete the job. Failed files normally need a new upload because the server does not retain your original recording.

The default limits are 20 files per job, 4 GB per file, and a three-hour recording cap. Hosts can change them; recordings under two hours are the intended use case. For phone installation and connection recovery, see [Mobile and Connectivity](https://github.com/aniketshedge/simple-transcription/wiki/Mobile-and-Connectivity). For symptoms and next steps, see [User Troubleshooting](https://github.com/aniketshedge/simple-transcription/wiki/User-Troubleshooting).
