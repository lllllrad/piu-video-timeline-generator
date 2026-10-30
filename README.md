# PIU Video Timeline Generator

Generate a paste-ready song timeline from a Pump It Up Phoenix gameplay video.

```sh
mise exec -- just auto 'https://www.youtube.com/watch?v=VIDEO_ID'
```

With mise installed, run `mise install` once to provision the tools in `mise.toml`, including uv and pnpm. Mise creates and activates `.venv`; recipes also support creating it without shell activation and install Python dependencies with `uv pip` on first use. On Linux, the requirements include the local ONNX OCR runtime. Later runs reuse the environment; dependency changes trigger an update. Initial setup needs network access.

The command downloads or opens the source, detects plays, recognizes songs, charts and result data, runs the default TypeScript format, prints the timeline, and saves everything under:

```text
.local/data/VIDEO_ID/
+-- raw/
+-- analysis/
|   +-- analysis.json
|   +-- evidence/
+-- output/
    +-- default.txt
```

Local files work the same way:

```sh
just auto '/absolute/path/to/recording.mp4'
```

Download without starting analysis when needed:

```sh
just fetch 'https://www.youtube.com/watch?v=VIDEO_ID'
```

Downloads show live progress, speed and estimated time remaining.

`fetch` and `auto` share the same cache. A later `auto` call reuses the completed video under `.local/data/<video-id>/raw/` without downloading it again.

To use a video downloaded from YouTube Studio as that cached source, move it into place with its URL or ID:

```sh
just import-studio VIDEO_ID '/absolute/path/to/studio-export.mp4'
just auto VIDEO_ID
```

The import refuses to overwrite an existing cached video. It moves the export to `.local/data/<video-id>/raw/`; the following `auto` command therefore makes no network request.

Automatic OCR uses macOS Vision on macOS or official PaddleOCR PP-OCRv5 models on Linux, running locally through ONNX Runtime. It requires a clearly visible Phoenix game screen. For a direct game capture or a different stream layout, specify the game rectangle:

```sh
just auto VIDEO --game-roi 0,0,1920,1080
```

On Linux, recipes install the ONNX Runtime and image-processing dependencies automatically from `requirements.txt`. Separate Korean/English recognition models and a lightweight text detector are downloaded on first use.

Linux automatically uses an available CUDA provider supported by the installed ONNX Runtime, with CPU fallback. The default dependency uses the CPU runtime. No device setting is needed for `just auto`. To force CPU inference:

```sh
PIU_OCR_DEVICE=cpu just auto VIDEO
```

Progress includes per-segment elapsed time, OCR image counts (including focused crops), cache reuse and OCR time.

Models are downloaded on first use into `.local/cache/paddleocr/`; pinned model revisions and SHA-256 checksums are verified before local inference. EasyOCR is available explicitly with `PIU_OCR_BACKEND=easyocr`. See [development](docs/development.md) for explicit device selection and validation limits.

## Visual play analysis

After `just auto`, analyze one play's visible notes and combo/judgment update timing:

```sh
just play VIDEO --segment 1
just play VIDEO --all
```

Open `.local/data/SOURCE_ID/play/segment-001/report.html` for the **Play evidence inspector**.
One original recording stays beside six tabs: notes and judgment, channel observations,
derivation, UCS transcription, warnings, and data/setup. Selecting a note or warning
shares its identity and recording position across tabs. Channel overlays map saved
head/body positions and documented popup/receptor regions onto the source video.
Frame navigation retains both recording time and source PTS. Named stage artifacts
keep observed tracks, coordinates, physical timing, musical decisions and input
associations separate. The inspector uses an explicitly composed view; HTML
rendering does not run inference. See [stage contracts](docs/derived-analysis.md).

The synchronized SVG chart keeps fixed-size colored notes while spacing changes.
Lime ranges show reconstructed targets; magenta ranges show display-based input
estimates or sustained hold recognition. Candidate connections are optional and
limited to 250 ms early / 500 ms late. MISS never supplies a press timestamp.
Warnings open their observed interval even when a track has no reconstructed target.
The derivation tab exposes selected observations, clock/beat results, processing,
policy and association records. UCS placements appear only from a saved draft;
source-note links require exact saved-analysis and unchanged UCS identities.
The inspector does not upload, re-encode or change media. `--all` writes a linked
`play/index.html` overview. See [the inspector](docs/evidence-inspector.md) and [play analysis](docs/play-analysis.md).

Saved-data modeling and report consumers run in TypeScript; Python handles media,
OCR and native image evidence. Registered coordinates and prepared report data
are reusable independently of beat reconstruction and HTML rendering. See
[derived analysis](docs/derived-analysis.md) for `just derive` and `just render`.

## Editable chart data

Official UCS downloads contain timing and BPM changes, **not the actual chart notes**. Create a separate local Git repository, then fill a draft from an already analyzed play:

```sh
just charts init
just charts list 'CHAOS AGAIN'
just charts add VIDEO --segment 19 --ucs-index CS349
just charts sync
```

The default repository is `../piu-chart-data`; override it with `PIU_CHART_DATA_DIR` or `just charts
--repo PATH ...`. The official catalogue maps songs to `CS...` download codes. An explicit code also
records the video's song title as an alias; later `just play` runs automatically register missing
charts, including when native analysis is reused. Ambiguous or unknown titles remain pending in
`chart-registration.json` until assigned a code. `sync` uses completed local play analyses without
rerunning note detection or metadata OCR.

Notes are stored as editable UCS text at `charts/CS349/S21/phoenix/chart.ucs`, with provenance,
unresolved placements and `unreviewed_draft` status in `metadata.json`. Reference music aligns song
time to original recording time using independent matching windows; it never changes playback speed.
If audio is missing or ambiguous, provide a reviewed `--song-start SECONDS` recording position.
Holds use UCS head/body/tail cells; censored endpoints and conflicting placements remain unresolved.
Existing chart directories are never overwritten. For an updated game chart, register a distinct
`--revision NAME`. Downloaded ZIPs and reference music stay in the ignored cache. See [chart
data](docs/chart-data.md).

The metadata also supports song-time `regions` with processing methods (`standard`, `exclude_timing`, `hold_state_only`), reasons/details, and scoped automatic-check exceptions. Reports show applied policies and retain unfiltered evidence alongside eligible check counts. `just charts validate` checks chart text and region settings; rebuilding a draft preserves human-authored regions. See [region configuration examples](docs/chart-data.md#region-processing-and-automatic-check-exceptions).

## Output formats

Choose a bundled or local format with the optional second argument:

```sh
just auto VIDEO scores
```

Bundled formats live in `formats/<name>/index.ts`. Personal formats live in `.local/formats/<name>/index.ts` and take precedence over a bundled format with the same name, including `default`. A format is an ordinary Node.js TypeScript program: it receives the saved `analysis.json` path as its first argument and writes its result to stdout.

The default format produces:

```text
00:00 auto-generated timeline started
01:23 Song Name D20 start
03:45 Song Name D20 end
```

When a recording contains different recognized player accounts (including players taking turns), the
default format adds `[Name]` to each play, omitting the account discriminator from presentation.
Analysis retains the full account identity. Rival comparison accounts are excluded from
participants. Simultaneous players retain separate names and charts. Unreadable identities remain
`Unknown player` when names are shown; one recognized account uses compact output, including when
its discriminator is unreadable in some plays. Two different recognized discriminators remain
distinct accounts.

Copy [formats/default/index.ts](formats/default/index.ts) to start a new format. Shared types and helpers are in [formats/lib/timeline.ts](formats/lib/timeline.ts). See [custom formats](docs/formats.md) for examples.

Analysis is reused. Running another format for the same source does not download the video or run OCR again.

## Review before publishing

Automatic boundaries identify gameplay; they do not prove that a publication boundary is silent. Check the video and audio before publishing:

- Start on a whole second during the silent full-screen song cover.
- End on a whole second during the black transition before the score screen.
- Starting playback at either boundary must not expose another game sound effect.

Unknown or conflicting OCR values remain unknown. The project never infers a YouTube offset from a filename or modifies original media.

## Requirements

- Python 3.12
- FFmpeg and ffprobe
- Node.js 24 or newer and pnpm (versions managed by mise)
- `just`
- Xcode Command Line Tools on macOS for Vision OCR

Developer setup and internal commands are documented in [docs/development.md](docs/development.md). Recognition assumptions and limitations are described in [docs/scene-and-ocr-notes.md](docs/scene-and-ocr-notes.md).
