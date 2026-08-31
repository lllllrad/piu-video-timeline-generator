# PIU Video Timeline Generator

YouTube timeline generator for typical Pump It Up playing video.

Detect song segments in Pump It Up gameplay recordings and produce a timeline for YouTube descriptions or comments.

## Scope and status

- First milestone: YouTube URL or local video → gameplay segment detection → song/chart recognition → timestamped text and JSON.
- Long-term goal: extract chart data and playable replays from video analysis.
- Implemented: URL/local media preparation, automatic Phoenix HUD discovery, gameplay candidate detection and decoded-frame boundary refinement, local song/chart OCR with multi-frame agreement, evidence-backed JSON/text output, independent-review evaluation, and the original manual-review workflow.
- Milestone 1 is implemented and validated on two development recordings: all 45 directly reviewed plays and song/chart pairs matched, with no unknown labels in the final runs. This is measured coverage of the reviewed set, not a universal accuracy claim. See [validation](docs/validation.md) for artifacts, timing uncertainty and known limits.
- Automatic recognition currently targets Phoenix game-screen layouts and runs on macOS with Vision OCR. It is not a universal camera-only or arbitrary-HUD detector. Unknown/conflicting labels remain unknown. See the validation notes before treating automatic output as publication-ready.
- Optional player-separated judgment counts, score/max combo, conditional title/detail templates, saved-frame result enrichment and JSON-only re-rendering are implemented. The default `single` selector follows the sole detected player on either side; see [result/template usage](docs/result-templates.md).

## Development environment

Run from the project root on macOS/Linux:

```sh
./scripts/bootstrap
just check
```

Bootstrap creates `.venv`, installs Python packages from `requirements-dev.txt`, generates the checkout-local Codex configuration, and runs the tests. It uses system Python 3.12, FFmpeg/ffprobe, Deno, and `just` by default.

If any of those executables are unavailable, opt into mise for pinned tool installation:

```sh
PIU_USE_MISE=1 ./scripts/bootstrap
```

Mise is only a tool installer here; it does not manage Python packages or project tasks. Its data lives under `.local/mise_home/`, while pip dependencies live in `.venv/`. Deno supports yt-dlp's YouTube JavaScript processing. Tools, caches, state, and temporary files remain inside the project; no global shell files or HOME changes are required.

Installation and YouTube access need network access and may require sandbox approval. Once installed, checks and local media processing work offline in the default sandbox. `check` includes unit tests and an integration test that generates a synthetic video and probes it.

Tool versions are pinned in `mise.toml`; Python dependencies are pinned in `pyproject.toml` and installed through the requirements files. To update a tool, edit `mise.toml` and rerun bootstrap with `PIU_USE_MISE=1`.

### Codex command environment

Bootstrap generates a Git-ignored `.codex/config.toml` for the current checkout. It adds mise shims to PATH and sets the same local cache/install paths as `scripts/env.sh`. It disables login-shell behavior to prevent login profiles from replacing PATH. Once Codex loads this trusted project's configuration, its shell tools can run:

```sh
just --list
just check
just fetch _OE47GBOvB0 --metadata-only
just probe '/absolute/path/to/studio-download.mp4'
```

Use non-login tool calls (`login: false`). Existing sessions may retain their previous environment: reload/restart the session after bootstrap if needed, or use `sh scripts/run.sh just check` in that stale session. With optional mise, `command -v just` resolves under `.local/mise_home/data/shims/`. Ordinary system commands such as `git add` need no wrapper. Project configuration is ignored for untrusted projects; this setup does not change trust, sandbox, or approval policies.

The generated configuration uses absolute paths discovered at bootstrap time, not committed machine-specific paths or shell-expanded `$PATH`/`$PWD`. Run `./scripts/bootstrap` once in each fresh clone or worktree. Rerunning it is safe: unchanged generated settings can be refreshed after relocation, while customized settings are preserved and bootstrap stops with instructions for manual merging. Installed binaries may also be location-dependent; a fresh checkout and bootstrap are preferable to copying `.local/` between machines. PATH includes project tools and standard system directories.

The entire `.codex/` directory is ignored by Git. The portable generator is `scripts/configure_codex.py`; after creating the venv, you can rerun it with `.venv/bin/python scripts/configure_codex.py`. Writing the protected `.codex/` directory may require approval in Codex. This does not grant broader sandbox permissions.

No shell activation is required. Just recipes invoke `sh scripts/run.sh ...`, which applies the project-local environment and then uses `.venv/bin/python`. The helper intentionally has no executable-bit requirement.

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
| [jYuRHc_D8zY](https://www.youtube.com/watch?v=jYuRHc_D8zY) | Unlabeled |
| [7BLKTVDLeYo](https://www.youtube.com/watch?v=7BLKTVDLeYo) | Unlabeled |
| [J0f9V-Qpijs](https://www.youtube.com/watch?v=J0f9V-Qpijs) | Unlabeled |
| [Q6ubf9mM2Q0](https://www.youtube.com/watch?v=Q6ubf9mM2Q0) | Unlabeled |

Comments are noisy references, not ground truth. Keep them separate from detector inputs. Do not copy their timestamps or optimize for exact agreement. Evaluate timing errors, missed segments, and false detections against manually reviewed video segments; choose tolerances after inspection. If a local export and YouTube VOD have different starting points or edits, verify alignment and record offsets.

## Next milestones

1. Locate the game screen with CV without predefined stream layouts, then normalize it to game-relative coordinates with YAML configuration and optional ROI overrides.
2. Broaden judgment/player-attribution validation, including genuine simultaneous two-player recordings; validate localization on unseen stream compositions and exhaustively annotated short plays.
3. Extend beyond the tested Phoenix layouts, add a portable OCR backend, and pursue chart/replay extraction after timeline accuracy is established.

Implementation knowledge is recorded in [scene and OCR field notes](docs/scene-and-ocr-notes.md): scene flow, player-side result differences, coordinate conventions, failure/summary handling and OCR regressions. See [game-screen and result design](docs/layout-and-result-design.md) for the remaining CV/YAML layout proposals, and [result/template usage](docs/result-templates.md) for executable TypeScript presentation.

## Analyze first, render when ready

```sh
# Store song/chart/timing/player evidence, without generating timeline text.
just analyze '/path/to/video.mkv' .local/outputs/analysis --judgments

# Review the structured result and its evidence, then choose presentation.
just format .local/outputs/analysis/analysis.json .local/outputs/timeline.txt
```

`analyze` writes `analysis.json`, checkpoints and evidence only. Without `--judgments`, it skips optional player-statistics OCR. It does not accept templates or output player selectors: analysis retains all detected slots, and presentation selects them later. To add judgments later, run `just results .local/outputs/analysis/analysis.json .local/outputs/enriched`; render `.local/outputs/enriched/analysis.json` when needed. No immediate timeline is required.

The analysis keeps the existing `segments` structure and `automatic_hud_ocr` method for compatibility, with `artifact_type: video_analysis`. It records detected gameplay intervals and sampled scene/OCR evidence, not an exhaustive classification of every scene in the video. The same JSON can be consumed by other tools; it is not a rendered timeline. `render` also accepts older `timeline.json` files without migration.

### Batch workflow and clean reruns

Keep a plain-text file containing one seed ID per line, with no Markdown escaping. Download/resume every input first, then analyze sequentially. Sequential processing makes the first failure visible and avoids running several full-video decoders and Vision OCR jobs at once.

```sh
while IFS= read -r video_id; do
  just fetch "$video_id" || break
done < .local/video-ids.txt

while IFS= read -r video_id; do
  just analyze "data/raw/$video_id/$video_id.mkv" ".local/outputs/$video_id-analysis-v1" || break
done < .local/video-ids.txt

while IFS= read -r video_id; do
  just render ".local/outputs/$video_id-analysis-v1/analysis.json" ".local/outputs/$video_id-publish-v1" || break
done < .local/video-ids.txt
```

Each output directory must be new. Generated artifacts belong under the ignored `.local/outputs/` directory. To start over without immediately deleting evidence, move it to a specifically named sibling and recreate it. Verify the backup before deleting it later.

```sh
mv .local/outputs .local/outputs-before-rerun
mkdir -p .local/outputs
```

If `.local/outputs-before-rerun` already exists, choose a different explicit name; do not overwrite it. Downloaded originals under `data/raw/` are independent and need not be fetched again. `just fetch` is resumable and preserves completed files. If analysis has missing labels but retained evidence, try `just relabel OLD_ANALYSIS NEW_OUTPUT` before decoding the full video again. Add `--judgments` to `analyze` only when player result statistics are needed; it is unnecessary for a simple YouTube timestamp list.

## Generate an automatic timeline (convenience)

```sh
# Offline local input: does not contact YouTube or upload frames.
just auto '/absolute/path/to/recording.mp4' '.local/outputs/automatic-run'

# URL/seed input: fetches or reuses the untrimmed media, then analyzes it.
just auto 'https://www.youtube.com/watch?v=uqM7H-OJp68' '.local/outputs/url-run'

# Direct game capture with no cameras/chat: specify the actual game rectangle.
just auto '/absolute/path/to/game-only.mp4' '.local/outputs/fullscreen-run' --game-roi 0,0,1920,1080
```

Automatic OCR requires macOS Vision and the existing `swiftc` command from Xcode Command Line Tools. The small helper is compiled into `.local/bin/` with module caches under `.local/cache/swift/`. No OCR service, account, model download or image upload is used. A restricted host may need permission to execute Vision; the CLI reports this instead of pretending OCR succeeded. `just check` runs offline unit/integration checks without Vision; `just check-ocr` separately exercises the actual host OCR engine.

The default crop is the seed stream's top-left game panel (1300x730 within a 1920x1080 recording, scaled with resolution). Pass `--game-roi` for another layout and exclude chat/cameras. HUD reference time is discovered automatically using STAGE text; no per-song timestamps or comments are inputs. The first ten minutes are sampled to locate the initial reference. Uncovered parts of the entire recording are then sampled every 30 seconds for alternate HUD positions, including the centered single-mode HUD. Each discovered position is scanned separately and overlapping candidates are checked for agreement. Short appearances between discovery samples can still be missed. An unsupported/missing initial HUD stops the run with an explicit error.

The pipeline scans keyframes for candidates, refines each boundary on a 0.1-second decoded-frame grid, and reads multiple selection/result screens. Title and chart areas are enlarged and recognized separately, with Korean/English title OCR and English chart OCR. Both left and right result badges are read; conflicting player charts remain unknown. Basic-mode `VERY HARD` badges retain their displayed label rather than being silently converted to a SINGLE chart. A confirmed result screen is preferred over selection; failed plays can use a matching song row in the play-summary screen. Labels require at least two agreeing frames; ambiguous or unavailable values are `null`. OCR engine confidence and agreement counts are evidence, not calibrated correctness probabilities.

Title agreement also accepts long, highly similar multi-frame OCR strings when one cluster has strictly greater support; short text, charts and tied clusters still require exact agreement. A single high-confidence title may be retained as review-required evidence so a uniquely matching summary row can recover its chart. Conversely, a known chart can recover a title only from a unique summary row. `just relabel OLD_ANALYSIS NEW_OUTPUT` applies these rules to retained OCR evidence without decoding media or changing already recognized labels.

Each new output directory contains `timeline.json`, `timeline.txt`, candidate/reference records, per-segment checkpoints and cropped evidence images with OCR results and source timestamps. The automatic schema is labeled `automatic_hud_ocr`, never `manual_video_review`. `needs_review` flags unknown labels, low OCR confidence or unrefined boundaries. Even unflagged labels can be wrong; inspect measured validation and supporting images. Automatic text uses local playback times; URL provenance is recorded, but a local-to-YouTube offset is not silently inferred. Original media is never trimmed, retimed or overwritten.

Result-title OCR preserves centered original text. If it fails or merges off-center background credits, a bright-text isolation pass can supply a centered title instead. Wholly Latin titles are additionally checked with English OCR. These heuristics preserve image evidence; they do not use a song-name dictionary or replace uncertain labels with reference annotations.

Outputs must be new directories. Analysis completion is marked by `analysis.json`, saved before any rendering. The `auto` convenience command additionally writes `timeline.json`, `timeline.txt`, `details.txt` and `rendered.json`. If analysis fails, partial evidence/checkpoints remain but no completed `analysis.json` is written. If rendering fails, the completed analysis remains usable with `just render`; a completed compatibility `timeline.json` is written only after rendering succeeds. Use a new output directory on retry. Large recordings take time and may need several gigabytes for the original media plus evidence. Keep output and reference artifacts in ignored directories.

To measure automatic output against a separately prepared video review:

```sh
just evaluate '.local/outputs/automatic-run/timeline.json' 'data/derived/reference.json' '.local/outputs/evaluation.json'
```

Reference files declare `method: independent_video_review`, source identity (`path`, `size_bytes`, `mtime_ns`), `coverage_seconds`, and reviewed `segments` with `start_range`, `end_range`, `song`, `chart`, and `evidence`. Boundary ranges preserve reviewer uncertainty. The evaluator reports misses, false positives, unknown fields, label correctness and distances outside those ranges. It does not treat unreviewed portions as verified or comment timestamps as ground truth.

## Player judgments and custom output

```sh
# Template fields automatically enable judgment extraction. No P1/P2 choice needed for one player.
just auto '/path/to/video.mkv' .local/outputs/with-counts --judgments

# Add judgments to a previous run using its saved game-result frames.
just results .local/outputs/automatic-run/timeline.json .local/outputs/enriched

# Change presentation without video decoding, OCR or network access.
just render .local/outputs/enriched/timeline.json .local/outputs/reformatted \
  --detail 'P {player.perfect} / G {player.great} / Miss {player.miss}'
```

`--player single` (default) selects the only recognized player regardless of side. Use `p1`, `p2` or `all` for explicit output. Counts remain separate; an unavailable or ambiguous player never borrows another player's data. Titles are written to `timeline.txt`, title/detail blocks to `details.txt`, and selection/missing-field warnings to `rendered.json`. See [the full guide](docs/result-templates.md) for conditions, placeholders, unknown policies and real-use workflows. Game-screen CV localization remains unimplemented; the existing default crop or `--game-roi` still applies.

## Generate a review-assisted timeline

This offline workflow renders **directly reviewed video segments**, not comments or automatically detected songs. No model, OCR package, or network request is needed for local inputs.

```sh
just record '/absolute/path/to/studio-download.mp4'
just review '/absolute/path/to/studio-download.mp4' '.local/review.json'
just frames '/absolute/path/to/studio-download.mp4' '.local/outputs/review-frames' --at 120 --at 130.5
# Edit .local/review.json using direct video inspection, then:
just timeline '/absolute/path/to/studio-download.mp4' '.local/review.json' '.local/outputs/run-001'
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

Boundary convention for a publishable song range:

- Choose the start as a whole second in the silent screen filled by the song cover, before gameplay begins. Starting playback there must not reveal another game sound effect.
- Choose the end as a whole second in the black transition after the song ends and before the score screen appears. Starting playback there must not reveal another game sound effect.
- Treat intervals as `[start, end)`, ordered and non-overlapping. Inspect both video and audio around each boundary and record any ambiguity in `evidence`.

The automatic HUD detector produces gameplay-oriented fractional boundary evidence and cannot prove the silence requirement. Save reviewed corrections in the local review JSON and run `just timeline` for publication; frame sampling alone cannot establish audio silence.

The outputs are `timeline.json` and `timeline.txt`. JSON retains reviewed values, source path, size, modification time, original container start, video timebases, frame rates and evidence. Text floors timestamps to whole seconds and renders `00:00 auto-generated timeline started`, then `MM:SS Song Chart start` and `MM:SS Song Chart end` (or hour-prefixed equivalents) for each song. Unknown songs render as `Unknown song`; unknown charts are omitted. An empty review still produces only the initial row. This is paste-ready timestamp text, not a guarantee that YouTube will activate chapters.

All review times are seconds from **local playback start**, not frame indices or absolute packet timestamps. Container duration metadata can include an initial offset, so playback duration is derived from video stream end times, falling back to a streaming packet scan when necessary. The original container duration and origin are retained separately. Variable-frame-rate media is not converted to constant frame rate. `frames.json` distinguishes requested times from the decoded frame's actual source PTS and playback time. Frame images retain source resolution; rotated media follows FFmpeg's default display orientation.

For a YouTube-aligned text list, set both `alignment.youtube_url` and a manually verified `alignment.offset_seconds` in the review, then append `--youtube` to `just timeline`. The relationship is `YouTube time = local playback time + offset`. Zero must be explicitly entered when the timelines match; no alignment is inferred from a filename or metadata. A single offset cannot describe edited/reordered videos. JSON always preserves local times, additionally recording aligned times when supplied.

Review files and output directories must not already exist; the commands never overwrite them or the source media. Invalid reviews are rejected before output creation. Media identity uses path, size, modification time and probe fields, not a cryptographic hash: moving or touching the media requires renewed review. Incomplete `.part` downloads are rejected. A failed frame extraction can leave a partial directory; it has no completed `frames.json` and should not be used as a finished sample set. Store reviews under `.local/` or `data/derived/` and generated outputs under `.local/outputs/` to keep them out of Git. A repository-root `outputs/` directory is deliberately visible to Git status.

## Experimental gameplay candidates

`detect` compares a small, fixed HUD region to a directly inspected gameplay reference frame. It uses grayscale mean absolute difference, short-gap merging and minimum-length filtering. It does not read comments, recognize songs, calibrate confidence, or produce final timestamps. Select a distinctive, static HUD patch (not a camera feed, chat, or changing score). Pixel coordinates refer to the encoded frame without auto-rotation.

```sh
# Example for the inspected 1920x1080 layout of seed _OE47GBOvB0 only.
# Do not assume this ROI/reference applies to other recordings.
just detect 'data/raw/_OE47GBOvB0/_OE47GBOvB0.mkv' '.local/outputs/candidates.json' \
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
