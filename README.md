# PIU Video Timeline Generator

YouTube timeline generator for typical Pump It Up playing video.

Detect song segments in Pump It Up gameplay recordings and produce a timeline for YouTube descriptions or comments.

## Scope and status

- First milestone: YouTube URL or local video → gameplay segment detection → song/chart recognition → timestamped text and JSON.
- Long-term goal: extract chart data and playable replays from video analysis.
- Implemented: URL/local media preparation, automatic Phoenix HUD discovery, gameplay candidate detection and decoded-frame boundary refinement, local song/chart OCR with multi-frame agreement, evidence-backed JSON/text output, independent-review evaluation, and the original manual-review workflow.
- Milestone 1 is implemented and validated on two development recordings: all 45 directly reviewed plays and song/chart pairs matched, with no unknown labels in the final runs. This is measured coverage of the reviewed set, not a universal accuracy claim. See [validation](docs/validation.md) for artifacts, timing uncertainty and known limits.
- Automatic recognition currently targets Phoenix game-screen layouts and runs on macOS with Vision OCR. It is not a universal camera-only or arbitrary-HUD detector. Unknown/conflicting labels remain unknown. See the validation notes before treating automatic output as publication-ready.

## Development environment

Run from the project root on macOS/Linux:

```sh
./scripts/bootstrap
./scripts/mise exec -- just check
```

The bootstrap installs mise into `.local/bin/mise` and pinned versions of just, Python, uv, Deno, yt-dlp, and FFmpeg/ffprobe under `.local/`. Deno supports yt-dlp's YouTube JavaScript processing. Installations, caches, state, and temporary files stay inside the project; no global shell files or HOME changes are required.

Installation and YouTube access need network access and may require sandbox approval. Once installed, checks and local media processing work offline in the default sandbox. `check` includes unit tests and an integration test that generates a synthetic video and probes it.

Tool versions are pinned in `mise.toml`. To update a tool, edit its version and rerun `./scripts/bootstrap`.

### Codex command environment

Bootstrap generates a Git-ignored `.codex/config.toml` for the current checkout. It adds mise shims to PATH and sets the same local cache/install paths as `scripts/env.sh`. It disables login-shell behavior to prevent login profiles from replacing PATH. Once Codex loads this trusted project's configuration, its shell tools can run:

```sh
just --list
just check
just fetch _OE47GBOvB0 --metadata-only
just probe '/absolute/path/to/studio-download.mp4'
```

Use non-login tool calls (`login: false`). Existing sessions may retain their previous environment: reload/restart the session if `command -v just` does not resolve to this project's `.local/share/mise/shims/just`. Project configuration is ignored for untrusted projects; this setup does not change trust, sandbox, or approval policies.

The generated configuration uses absolute paths discovered at bootstrap time, not committed machine-specific paths or shell-expanded `$PATH`/`$PWD`. Run `./scripts/bootstrap` once in each fresh clone or worktree. Rerunning it is safe: unchanged generated settings can be refreshed after relocation, while customized settings are preserved and bootstrap stops with instructions for manual merging. Installed binaries may also be location-dependent; a fresh checkout and bootstrap are preferable to copying `.local/` between machines. PATH includes project tools and standard system directories.

The entire `.codex/` directory is ignored by Git. The portable generator is `scripts/configure_codex.py`; after installing tools, you can rerun it with `./scripts/mise exec -- python scripts/configure_codex.py`. Writing the protected `.codex/` directory may require approval in Codex. This does not grant broader sandbox permissions.

Outside Codex, or before configuration reload, use `./scripts/mise exec -- just ...`. The wrapper applies the local environment on every invocation, without persistent `activate` state. Avoid calling `.local/bin/mise` directly unless the project environment is already set. The just recipes delegate to this wrapper as well.

## Prepare inputs

```sh
# Inspect metadata without downloading the video.
just fetch _OE47GBOvB0 --metadata-only

# Download the best available quality using a seed ID or YouTube URL.
just fetch _OE47GBOvB0
just fetch 'https://www.youtube.com/live/uqM7H-OJp68'

# Optional: increase fragment concurrency (default 4, maximum 16).
just fetch _OE47GBOvB0 --concurrent-fragments 8

# Collect reference comments separately, without downloading the video.
just fetch 5l0xgojfQGs --comments

# Inspect a YouTube Studio export without a network request.
just probe '/absolute/path/to/studio-download.mp4'
```

Videos and source metadata are stored in `data/raw/<video-id>/`; metadata containing comments is stored in `data/labels/<video-id>/`. These directories are excluded from Git. The entire seed list is never downloaded automatically. Long videos can require substantial disk space. Active livestreams are excluded; use completed VODs. Repeated downloads preserve completed files and use yt-dlp's default partial-download resume behavior.

Only download and analyze videos you own or have permission to use. Authentication or bot checks may prevent downloads; the scripts do not automatically read browser cookies. YouTube Studio exports provide a local-input alternative. Preserve the original media and timestamps without trimming or overwriting it.

## Initial dataset

Machine-readable manifest: [`data/seeds.json`](data/seeds.json). Mobile/live URLs and sharing parameters are normalized to watch URLs with the same video IDs.

| Video ID | Label status |
| --- | --- |
| [_OE47GBOvB0](https://www.youtube.com/watch?v=_OE47GBOvB0) | Unlabeled |
| [uqM7H-OJp68](https://www.youtube.com/watch?v=uqM7H-OJp68) | Unlabeled |
| [u8-FKR2E7KQ](https://www.youtube.com/watch?v=u8-FKR2E7KQ) | Unlabeled |
| [5l0xgojfQGs](https://www.youtube.com/watch?v=5l0xgojfQGs) | Approximate reference labels in comments |
| [6DqcuWMLIE4](https://www.youtube.com/watch?v=6DqcuWMLIE4) | Approximate reference labels in comments |
| [01n1Q6W0jOo](https://www.youtube.com/watch?v=01n1Q6W0jOo) | Approximate reference labels in comments |

Comments are noisy references, not ground truth. Keep them separate from detector inputs. Do not copy their timestamps or optimize for exact agreement. Evaluate timing errors, missed segments, and false detections against manually reviewed video segments; choose tolerances after inspection. If a local export and YouTube VOD have different starting points or edits, verify alignment and record offsets.

## Next milestones

1. Expand validation to untouched recordings and exhaustively annotated short plays.
2. Extend beyond the tested Phoenix layouts and add a portable OCR backend.
3. Extend to chart/replay extraction only after timeline accuracy is established.

## Generate an automatic timeline

```sh
# Offline local input: does not contact YouTube or upload frames.
just auto '/absolute/path/to/recording.mp4' 'outputs/automatic-run'

# URL/seed input: fetches or reuses the untrimmed media, then analyzes it.
just auto 'https://www.youtube.com/watch?v=uqM7H-OJp68' 'outputs/url-run'

# Direct game capture with no cameras/chat: specify the actual game rectangle.
just auto '/absolute/path/to/game-only.mp4' 'outputs/fullscreen-run' --game-roi 0,0,1920,1080
```

Automatic OCR requires macOS Vision and the existing `swiftc` command from Xcode Command Line Tools. The small helper is compiled into `.local/bin/` with module caches under `.local/cache/swift/`. No OCR service, account, model download or image upload is used. A restricted host may need permission to execute Vision; the CLI reports this instead of pretending OCR succeeded. `just check` runs offline unit/integration checks without Vision; `just check-ocr` separately exercises the actual host OCR engine.

The default crop is the seed stream's top-left game panel (1300x730 within a 1920x1080 recording, scaled with resolution). Pass `--game-roi` for another layout and exclude chat/cameras. HUD reference time is discovered automatically using STAGE text; no per-song timestamps or comments are inputs. The first ten minutes are sampled to locate the initial reference. Uncovered parts of the entire recording are then sampled every 30 seconds for alternate HUD positions, including the centered single-mode HUD. Each discovered position is scanned separately and overlapping candidates are checked for agreement. Short appearances between discovery samples can still be missed. An unsupported/missing initial HUD stops the run with an explicit error.

The pipeline scans keyframes for candidates, refines each boundary on a 0.1-second decoded-frame grid, and reads multiple selection/result screens. Title and chart areas are enlarged and recognized separately, with Korean/English title OCR and English chart OCR. Both left and right result badges are read; conflicting player charts remain unknown. Basic-mode `VERY HARD` badges retain their displayed label rather than being silently converted to a SINGLE chart. A confirmed result screen is preferred over selection; failed plays can use a matching song row in the play-summary screen. Labels require at least two agreeing frames; ambiguous or unavailable values are `null`. OCR engine confidence and agreement counts are evidence, not calibrated correctness probabilities.

Each new output directory contains `timeline.json`, `timeline.txt`, candidate/reference records, per-segment checkpoints and cropped evidence images with OCR results and source timestamps. The automatic schema is labeled `automatic_hud_ocr`, never `manual_video_review`. `needs_review` flags unknown labels, low OCR confidence or unrefined boundaries. Even unflagged labels can be wrong; inspect measured validation and supporting images. Automatic text uses local playback times; URL provenance is recorded, but a local-to-YouTube offset is not silently inferred. Original media is never trimmed, retimed or overwritten.

Result-title OCR preserves centered original text. If it fails or merges off-center background credits, a bright-text isolation pass can supply a centered title instead. Wholly Latin titles are additionally checked with English OCR. These heuristics preserve image evidence; they do not use a song-name dictionary or replace uncertain labels with reference annotations.

Outputs must be new directories. If a run fails, its partial directory is retained for diagnosis and contains no completed `timeline.json`; use a new directory on retry. Large recordings take time and may need several gigabytes for the original media plus evidence. Keep output and reference artifacts in ignored directories.

To measure automatic output against a separately prepared video review:

```sh
just evaluate 'outputs/automatic-run/timeline.json' 'data/derived/reference.json' 'outputs/evaluation.json'
```

Reference files declare `method: independent_video_review`, source identity (`path`, `size_bytes`, `mtime_ns`), `coverage_seconds`, and reviewed `segments` with `start_range`, `end_range`, `song`, `chart`, and `evidence`. Boundary ranges preserve reviewer uncertainty. The evaluator reports misses, false positives, unknown fields, label correctness and distances outside those ranges. It does not treat unreviewed portions as verified or comment timestamps as ground truth.

## Generate a review-assisted timeline

This offline workflow renders **directly reviewed video segments**, not comments or automatically detected songs. No model, OCR package, or network request is needed for local inputs.

```sh
just record '/absolute/path/to/studio-download.mp4'
just review '/absolute/path/to/studio-download.mp4' '.local/review.json'
just frames '/absolute/path/to/studio-download.mp4' 'outputs/review-frames' --at 120 --at 130.5
# Edit .local/review.json using direct video inspection, then:
just timeline '/absolute/path/to/studio-download.mp4' '.local/review.json' 'outputs/run-001'
```

`review` creates a manifest with an empty `segments` list. Replace that list with reviewed entries such as:

```json
[
  {
    "start_seconds": 120.25,
    "end_seconds": 241.5,
    "song": "Example song",
    "chart": "D20",
    "confidence": null,
    "evidence": "Direct video review: gameplay begins at 120.25s; result transition at 241.5s."
  }
]
```

The example values are illustrative, not labels for the seed videos. Use `null` for an unknown song, chart, or confidence. Confidence, when supplied, is a reviewer estimate in [0, 1], not a calibrated detector probability. Evidence is required; the program cannot verify that the reviewer actually inspected the video.

Boundary convention: start at the first visible playable gameplay frame (not song selection or the loading screen); end at the first frame after gameplay disappears. Intervals are `[start, end)`, ordered and non-overlapping. Record any ambiguity in evidence. Frame sampling is for inspection and does not establish exact boundaries automatically.

The outputs are `timeline.json` and `timeline.txt`. JSON retains fractional seconds, source path, size, modification time, original container start, video timebases and frame rates, and evidence. Text floors timestamps to whole seconds, rendering `MM:SS Song [Chart]` or `H:MM:SS Song [Chart]`. Unknown songs render as `Unknown song`; unknown charts are omitted. Empty reviewed lists produce empty text, not invented detections. This is timestamp-list text, not a guarantee that YouTube will activate chapters.

All review times are seconds from **local playback start**, not frame indices or absolute packet timestamps. Container duration metadata can include an initial offset, so playback duration is derived from video stream end times, falling back to a streaming packet scan when necessary. The original container duration and origin are retained separately. Variable-frame-rate media is not converted to constant frame rate. `frames.json` distinguishes requested times from the decoded frame's actual source PTS and playback time. Frame images retain source resolution; rotated media follows FFmpeg's default display orientation.

For a YouTube-aligned text list, set both `alignment.youtube_url` and a manually verified `alignment.offset_seconds` in the review, then append `--youtube` to `just timeline`. The relationship is `YouTube time = local playback time + offset`. Zero must be explicitly entered when the timelines match; no alignment is inferred from a filename or metadata. A single offset cannot describe edited/reordered videos. JSON always preserves local times, additionally recording aligned times when supplied.

Review files and output directories must not already exist; the commands never overwrite them or the source media. Invalid reviews are rejected before output creation. Media identity uses path, size, modification time and probe fields, not a cryptographic hash: moving or touching the media requires renewed review. Incomplete `.part` downloads are rejected. A failed frame extraction can leave a partial directory; it has no completed `frames.json` and should not be used as a finished sample set. Store reviews under `.local/` or `data/derived/` and outputs under `outputs/` to keep them out of Git.

## Experimental gameplay candidates

`detect` compares a small, fixed HUD region to a directly inspected gameplay reference frame. It uses grayscale mean absolute difference, short-gap merging and minimum-length filtering. It does not read comments, recognize songs, calibrate confidence, or produce final timestamps. Select a distinctive, static HUD patch (not a camera feed, chat, or changing score). Pixel coordinates refer to the encoded frame without auto-rotation.

```sh
# Example for the inspected 1920x1080 layout of seed _OE47GBOvB0 only.
# Do not assume this ROI/reference applies to other recordings.
just detect 'data/raw/_OE47GBOvB0/_OE47GBOvB0.mkv' 'outputs/candidates.json' \
  --roi 180,0,76,20 --reference-at 140 --limit 600
```

Create the output parent directory first. Defaults: 2-second sampling grid, match threshold 0.9, minimum run 20 seconds, maximum internal gap 4 seconds. `--limit` bounds an exploratory scan; omit it to scan the entire video. The matcher decodes keyframes only, so its grid timestamps are approximate and can shift by the source keyframe spacing in addition to the sampling step. Long keyframe gaps, seeking, VFR, HUD animation, layout changes and single/double transitions can cause misses or false positives. `mean_match_score` is image similarity, **not a probability**. Inspect `samples` and missed sections as well as detected intervals.

The candidate JSON deliberately uses method `experimental_hud_template`, which the final generator rejects. Use `just frames` and direct video inspection to establish actual boundaries, then enter reviewed intervals and evidence in a separately created review manifest. Synthetic tests verify matching mechanics, not real-world detection accuracy.

See [validation](docs/validation.md) for automatic-pipeline measurements, observed timing errors, local artifacts and remaining limitations.

## References

- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [mise installation](https://mise.jdx.dev/installing-mise.html)
- [mise directory configuration](https://mise.jdx.dev/directories.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
