# Processing and Output

[← Home](https://github.com/aniketshedge/simple-transcription/wiki/Home)

Each recording is handled locally by the server, one file at a time. The app reports stages rather than pretending that every stage has a predictable share of the whole job.

| Stage | What happens |
| --- | --- |
| Upload | The browser sends bytes to the server; this progress is measured. |
| Queue | Files run one at a time. The completed-file count describes job progress. |
| Prepare audio | The server validates the media and decodes its first audio track to 16 kHz mono audio. This is preparation, not an output download. |
| Load transcription model | WhisperX loads the selected English model. First use may download weights; later use can use cached weights. |
| Transcribe | WhisperX recognizes English speech locally. |
| Load timestamp model / Align timestamps | An English alignment model refines where recognized speech occurs. Internal word alignment does not add word lines to TXT. |
| Load speaker model / Identify speakers (optional) | When enabled, the server groups voices and assigns anonymous labels. This needs host configuration. If no speech segments are found, later alignment or speaker work may be skipped. |
| Save transcript / Complete | TXT and JSON are saved, then temporary source and decoded audio are removed. |

## Progress and ETA

The UI’s exact processing labels include `Preparing audio`, `Loading transcription model`, `Transcribing`, `Loading timestamp model`, `Aligning timestamps`, `Loading speaker model`, `Identifying speakers`, and `Saving transcript`. Loading stages do not always have a measurable percentage. Percentages reset for each stage. An ETA is an estimate for the current stage only; it starts only after enough measured progress, and excludes later stages, model downloads, and queued files. Speaker stages contain uneven substeps, so their estimate can move substantially.

## Output files

The TXT format contains source/model metadata, warnings, and segment text with timestamps. It omits word timings and confidence scores. Times are relative to the recording; missing times are shown as `unknown`. Speaker IDs are optional, anonymous, local to one file, and not verified identities.

TXT excerpt (metadata and warnings omitted):

```text
[00:00:03.240 --> 00:00:04.100] SPEAKER_00: Hello there.
[00:00:04.500 --> 00:00:06.200] SPEAKER_01: Let's start the meeting.
```

JSON retains the full structured results where available, including word timings and confidence information. ZIP downloads contain both formats and use unique prefixes when filenames repeat. Existing TXT files keep the format used when they were generated.

Recognition and alignment create intermediate checkpoints. If alignment or speaker labeling fails, usable text can remain available with a warning; a downloadable checkpoint explicitly says processing is incomplete and is not proof that the job is finished. See [User Troubleshooting](https://github.com/aniketshedge/simple-transcription/wiki/User-Troubleshooting) or [Configuration and Speakers](https://github.com/aniketshedge/simple-transcription/wiki/Configuration-and-Speakers) next.
