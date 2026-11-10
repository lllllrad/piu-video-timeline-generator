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

Successful analysis updates remove superseded analysis versions and abandoned builds. Original recordings and current native evidence
are preserved. See [local storage](docs/local-storage.md).

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

Interrupted downloads resume on the next `fetch` or `auto` call. Format streams
such as `.f299.mp4` remain intermediate files until video and audio are merged;
their `.part` and `.ytdl` files are preserved for yt-dlp continuation. Visual
recognition uses video; the recording audio supports official-song alignment
for beat reconstruction and UCS transcription.

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

After `just auto`, play analysis identifies a compatible image bank from the
active candidates in the separate skin repository. Explicit `just skins select`
profiles or `--note-skin PATH` take precedence. Unknown or ambiguous skins fail
with retained image evidence; existing reports remain readable:

```sh
just play VIDEO --segment 1
just play VIDEO --all
```

The generated `report.html` is a small entry page for the local evidence editor.
Run `just editor SOURCE --segment 1` to open the original recording beside a
bounded chart view and review panel. Saved popup, receptor, motion and processing
channels retain original recording time and source PTS. Full stage artifacts stay
separate and downloadable; selecting evidence does not rerun inference.
`--all` and background replay maintain a linked `play/index.html` overview.
See [the interval editor](docs/review-editor.md), [execution contracts](docs/analysis-stage-contracts.md)
and [play analysis](docs/play-analysis.md).

Saved-data modeling and report consumers run in TypeScript; Python handles media,
OCR and native image evidence. Registered coordinates and prepared report data
are reusable independently of beat reconstruction and HTML rendering. See
[derived analysis](docs/derived-analysis.md) for `just derive` and `just render`.

Independent channel acquisition can run before chart or input analysis:

```sh
just observe --acquire --jobs 2
```

It stores source-bound timelines, compact spatial masks and ungrouped detector
observations under `.local/data/SOURCE/observations/`. Compatible detector observations are reused directly. Changed pixel detectors decode
the original recording; decoded RGB frames are never cached. A detector failure
preserves the acquired timeline and masks. See [independent observations](docs/independent-observations.md).

## Interval review editor

Open saved evidence beside the original recording and edit source-bound interval truth:

```sh
just editor-build
just editor VIDEO --segment 1
```

The desktop browser editor uses English labels. Notes, censored holds, weighted/nonuniform
ticks and independent scroll changes stay under `.local/`, separate from automatic evidence.
Default reports are small entry pages; the server fetches bounded evidence windows instead
of embedding the full analysis in HTML. Shared editor primitives are built as a tarball from
a pinned local DCM checkout. See [setup, data model and limits](docs/review-editor.md).

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
unresolved placements and `unreviewed_draft` status in `metadata.json`. Official UCS timing defines
the musical clock. Reference music locates its audio origin using independent matching windows;
visual evidence must separately support the common video offset before audio-aligned transcription.
Neither alignment changes playback speed. If alignment is unresolved, provide a reviewed
`--song-start SECONDS` video position. See [audio/video alignment limits](docs/chart-data.md#reusing-the-bounded-common-song-phase).
Holds use UCS head/body/tail cells; censored endpoints and conflicting placements remain unresolved.
Untouched `unreviewed_draft` charts merge contributions from additional recordings. Reviewed or manually edited UCS files remain protected. For an updated game chart, register a distinct
`--revision NAME`. Downloaded ZIPs and reference music stay in the ignored cache. See [chart
data](docs/chart-data.md).

The metadata also supports song-time `regions` with processing methods (`standard`, `exclude_timing`, `hold_state_only`), reasons/details, and scoped automatic-check exceptions. Reports show applied policies and retain unfiltered evidence alongside eligible check counts. `just charts validate` checks chart text and region settings; rebuilding a draft preserves human-authored regions. See [region configuration examples](docs/chart-data.md#region-processing-and-automatic-check-exceptions).

Reusable note-skin images also live in the separate data repository, under
`skins/banks/<skin>/<revision>/`. `just skins publish`, `list`, `select` and
`validate` manage exact image references, review status and portable segment
selections. Candidates can be built locally before publication. See
[versioned skin assets](docs/note-skin-images.md#versioned-reference-assets).

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
