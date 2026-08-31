# PIU Video Timeline Generator

Generate a song timeline from a Pump It Up gameplay recording. The project can prepare a YouTube or local video, detect Phoenix gameplay segments, recognize song and chart labels, retain review evidence, and produce paste-ready timestamp text.

Automatic recognition is designed for recordings that contain a clear Phoenix game screen. It uses local macOS Vision OCR and is not a general camera-view or arbitrary-layout recognizer. Always review publication-sensitive boundaries and labels.

## Requirements

- Python 3.12
- FFmpeg and ffprobe
- Deno
- `just`
- macOS with Xcode Command Line Tools for automatic OCR

Set up the project from its root:

```sh
./scripts/bootstrap
```

If the required tool versions are not installed, the project can install pinned copies locally:

```sh
PIU_USE_MISE=1 ./scripts/bootstrap
```

Project tools, caches and generated output stay under `.local/`. Python packages are installed into `.venv/`.

## Generate a timeline

For a local recording:

```sh
just auto '/absolute/path/to/recording.mp4' '.local/outputs/run-001'
```

For a YouTube URL or video ID:

```sh
just auto 'https://www.youtube.com/watch?v=VIDEO_ID' '.local/outputs/run-001'
```

If the video is a direct game capture, provide the full game rectangle:

```sh
just auto '/absolute/path/to/recording.mp4' '.local/outputs/run-001' \
  --game-roi 0,0,1920,1080
```

The output directory contains structured JSON, timeline text, checkpoints and cropped evidence. Output directories must be new; existing files are never overwritten.

## Analyze first, format later

Keep detection and OCR separate from presentation when you want to inspect or reuse the result:

```sh
just analyze '/absolute/path/to/recording.mp4' '.local/outputs/analysis'
just format '.local/outputs/analysis/analysis.json' '.local/outputs/timeline.txt'
```

Add `--judgments` to `analyze` to extract player-separated result counts. Counts can also be added later from saved evidence:

```sh
just results '.local/outputs/analysis/analysis.json' '.local/outputs/with-judgments'
```

The executable TypeScript formatter can contain arbitrary output logic:

```sh
just format analysis.json timeline.txt .local/my-timeline.ts
```

Start from [templates/timeline.ts](templates/timeline.ts). Typed JSON interfaces, validation and timestamp helpers are in [templates/timeline_utils.ts](templates/timeline_utils.ts).

The default text format is:

```text
00:00 auto-generated timeline started
01:23 Song Name D20 start
03:45 Song Name D20 end
```

## Review publication boundaries

Automatic HUD boundaries describe detected gameplay and do not prove that a boundary is silent. For a publishable range, inspect both video and audio:

- Start on a whole second during the silent screen filled by the song cover, before gameplay begins.
- End on a whole second during the black transition after the song finishes and before the score screen.
- Starting playback at either boundary must not expose another game sound effect.

Create and fill a local review manifest when corrections are needed:

```sh
just review '/absolute/path/to/recording.mp4' '.local/review.json'
just frames '/absolute/path/to/recording.mp4' '.local/review-frames' --at 120 --at 130.5
just timeline '/absolute/path/to/recording.mp4' '.local/review.json' '.local/outputs/reviewed'
```

Review times are seconds from local playback start. If a local export and YouTube use different timelines, record an explicit alignment offset in the review; the project never infers one from filenames or duration.

## Input preparation

Inspect or fetch media with:

```sh
just probe '/absolute/path/to/studio-export.mp4'
just fetch VIDEO_ID --metadata-only
just fetch VIDEO_ID
```

YouTube media is stored under `data/raw/`. Reference comments, when explicitly requested, are stored separately under `data/labels/` and are never detector inputs:

```sh
just fetch VIDEO_ID --comments
```

Only download and analyze recordings you own or have permission to use. Original media is never trimmed, retimed or overwritten.

## Limitations and further documentation

- Unknown or conflicting OCR values remain unknown.
- The default crop targets the known stream layout; use `--game-roi` for other layouts.
- Automatic OCR currently requires macOS Vision.
- Evidence and review flags should be inspected before publication.

Additional documentation:

- [Timeline formatting and player results](docs/result-templates.md)
- [Scene and OCR notes](docs/scene-and-ocr-notes.md)
- [Validation and known limits](docs/validation.md)
- [Development guide](docs/development.md)
