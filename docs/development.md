# Development

## Setup

The project requires Python 3.12, FFmpeg, Node.js 24 or newer and `just`.

```sh
mise install
mise exec -- just check
mise exec -- just auto SOURCE
```

Recipes automatically create `.venv` and install the project dependencies. `requirements.txt` includes ONNX Runtime, PyYAML and polygon-processing dependencies on Linux using platform markers. Installation is serialized across concurrent recipes and cached under `.venv`; changes to dependency declarations trigger an update. Failed installations are retried on the next run. If the required tools are already on PATH, `just` can be used directly.

No shell activation is required; recipes use `scripts/run.sh` to apply project-local cache paths and invoke `.venv` explicitly.

Codex-only environment generation and optional mise installation are documented in [codex-environment.md](codex-environment.md). They are not part of normal project setup.

## Architecture

- `workflow.py` owns the public `just auto` flow, stable source IDs and `.local/data/` layout.
- `media.py` prepares YouTube media with yt-dlp or inspects local input.
- `auto_timeline.py` detects gameplay, refines boundaries and saves structured evidence.
- `ocr.py` adapts Vision or PaddleOCR to normalized, top-left coordinates. Official PaddleOCR PP-OCRv5 detection and Korean/English recognition run through `paddle_ocr.py` on Linux. Sessions and a bounded cache of exact image-content results are reused within a process; models stay under `.local/cache/`. Cache entries distinguish language, backend, device and pinned model/preprocessing identity, return independent result objects, and retain each observation's original source timestamp.
- `screen_ocr.py` reads English UI regions for scene routing. Linux OCR crops a decoded image with Pillow; Vision uses FFmpeg without adding a Python imaging dependency.
- `recognition.py` classifies observed screens and parses layout-specific fields.
- `evidence.py` resolves labels, player identity and stage-row associations across a credit.
- `credits.py` samples screen transitions inside gameplay gaps and groups plays using observed credit boundaries.
- `result_stats.py` extracts per-player result fields only from per-song results.
- `play_holds.py` acquires small native-frame body/receptor features, reconstructs long-note endpoints and sustained recognition spans, and projects a hold-aware chart without converting ticks into presses. `play_candidates.py` constrains review alternatives using refresh ownership, processed-row order and per-lane receptor evidence.
- `play_analysis.py` orchestrates opt-in visual analysis and caches evidence; `play_report.py` renders a self-contained local HTML view. `play_ranges.py` derives review-only alternative refresh intervals and conditional neighboring-row bounds from saved evidence without changing confirmed associations or reacquiring frames.
- `play_judgments.py` learns a bounded set of judgment-word templates, detects native-frame label/animation refreshes independently of combo visibility, and merges evidence without duplicate note assignments. MISS never becomes a physical input timestamp.
- `play_frames.py` streams native decoded frames with original PTS and no FPS conversion.
- `play_tracking.py` locates colored note-head outlines, bridges bounded UI occlusions, distinguishes repeated render frames from nonlinear motion, learns combo digit templates and aligns judged rows with confirmed combo updates. A chord occupies one judged row. Compatible native observations can be refitted without frame decoding or OCR; font examples are reusable across plays from unchanged source media. It does not equate display refresh with physical switch input.
- `formats/` contains Node.js TypeScript presentation programs. `formats/lib/timeline.ts` separates song labels, player names and recording-aware segment labels; both bundled formats share the same automatic name-visibility policy. See [custom formats](formats.md).
- `timeline.py`, `evaluate.py` and `relabel_analysis.py` are internal review and diagnostic tools.

Analysis is authoritative and presentation is disposable. A format reads `analysis.json`; it does not trigger recognition or mutate evidence.
Analyzer changes that affect saved results increment `ANALYSIS_VERSION`. `just auto` rebuilds an older cache into a unique temporary directory and replaces it only after the new analysis succeeds. Source size/mtime, explicit game ROI and OCR backend/device changes invalidate the cache too. A per-source advisory lock prevents concurrent writers on macOS/Linux. Existing results are retained in `analysis.previous-*`; interrupted builds remain in `analysis.build-*` for diagnosis. Promotion rewrites nested evidence paths to their final location. Original media is never rewritten.

The metadata planner schedules OCR from screen transitions before acquiring text. Two small grayscale frames per second locate changes only in the bounded gaps around gameplay; OCR reads transition representatives plus sparse guard samples. When no changes are found, song/chart labels remain unresolved, or no result screen is observed, fixed-offset sampling provides coverage. Retained OCR and source timestamps are preserved. Dedicated result-number OCR reads at most six source frames distributed across the observed result duration, preferring frames with directly observed numeric rows over entrance animations, independent of the number of decoded frames. Existing contextual and contrast recovery channels remain bounded to six source frames each.

Screen routing reads fixed UI regions in English rather than unconditionally recognizing the full game image in Korean and English. A carousel of available levels is classified as `browse`, which can supply identity/boundary evidence but never a selected chart. Aligned judgment captions and numeric rows can establish a result without the animated SCORE heading. Frames without the fixed account header or judgment UI read only a small control-text crop, retaining start/mode/failure detection without scanning names/chart bands over song art. Unknown screens receive at most two new full-image OCR attempts per pre/post-game window. Song/chart recovery reads at most six new source frames per eligible scene and window, stopping per-song title/chart reads when distinct frames agree; frames after an observed return to browsing/selection cannot supply result metadata. Unreadable values remain unknown. Directly recognized result/browse screens seed small visual UI templates. Matching fixed judgment-caption color masks or the carousel band can route subsequent or earlier representatives without OCR. This reuses only the screen kind, never title/account/numeric text. Later representatives are examined first so settled UI can route entrance animations. Selected title/identity/statistics frames still read their own UI/account/rival evidence. Templates are local to one play, and unknown layouts remain unknown. Unfamiliar layouts can still exceed these routing assumptions and need representative-video validation.

Progress reports include segment elapsed time, inferred/cached OCR image counts and time inside OCR. These counts include individual UI/title/name/numeric crops, not just full source frames. Exact-content cache hits reuse inference only: their observations keep distinct actual source timestamps and are never presented as additional decoded frames.

Source-verified acquisition is reusable independently of the analyzer release or OCR engine: original media identity and game ROI must match and the saved profile/candidate artifacts must exist. An OCR identity change invalidates text, screen decisions and parsed statistics while preserving captured images, original PTS, decoded boundaries and transition plans. Existing image crops are reused. Only the new complete analysis is promoted.

Frame decoding, visual change detection and OCR have separate responsibilities. Gameplay interval detection uses visual HUD matching. Future note-position tracking should consume decoded gameplay frames and their original timestamps directly; it must not call metadata OCR for every frame. OCR belongs to selected metadata observations around gameplay, with separate language and region-specific recovery. The opt-in `just play` path consumes native frames independently of metadata sampling; see [play analysis](play-analysis.md).

## Commands

The public interface intentionally stays small:

```sh
just auto SOURCE [FORMAT]
just play SOURCE --segment N
just play SOURCE --all
just fetch URL_OR_ID
just import-studio URL_OR_ID VIDEO_PATH
just check
just check-ocr
```

Private recipes beginning with `_` support direct review and diagnostics without appearing in `just --list`.

## Verification

```sh
just check
node formats/default/index.ts PATH/TO/analysis.json
```

`just check` is offline after the initial dependency setup and includes unit tests plus synthetic FFmpeg integration. `just check-ocr` separately exercises the host Vision implementation.

## Data and recognition rules

- Keep downloaded media, analysis output, caches and personal formats under `.local/`.
- Never overwrite or retime source media.
- Preserve unknown and conflicting OCR values as `null` or explicit field states.
- Keep P1 and P2 result evidence separate.
- Keep local playback time distinct from YouTube time unless an explicit reviewed offset exists.
- Automatic gameplay boundaries do not establish silent publication boundaries.

Design observations are in [scene-and-ocr-notes.md](scene-and-ocr-notes.md) and [layout-and-result-design.md](layout-and-result-design.md). Keep corpus-specific validation reports and execution logs under ignored `.local/`; commit reusable tests and design guidance only.

## Linux and accelerator setup

Recipes install the Linux inference dependencies automatically from `requirements.txt`. The default backend runs the official `PP-OCRv5_mobile_det`, `korean_PP-OCRv5_mobile_rec` and `en_PP-OCRv5_mobile_rec` ONNX exports. Model downloads use pinned Hugging Face revisions and verified SHA-256 checksums under `.local/cache/paddleocr/`. No PaddlePaddle framework, GUI OpenCV or PyTorch is required for the default OCR path. macOS metadata OCR uses native Vision; visual play analysis also uses NumPy and OpenCV.

The Korean model includes all modern Hangul syllables, including syllables absent from EasyOCR’s Korean vocabulary. BGR normalization, line-height resizing, padding, polygon expansion and CTC decoding follow the model export definitions. Text lines are batched by width; input images and their timestamps are unchanged. No song-name dictionary or spelling correction is applied. Chart agreement requires at least two source frames with OCR confidence of .7 or higher; repeated weak digits remain unresolved. References: [Korean recognizer](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec_onnx), [English recognizer](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec_onnx), [text detector](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det_onnx).

- `PIU_OCR_BACKEND=auto` selects Vision on macOS and PaddleOCR elsewhere.
- `PIU_OCR_BACKEND=vision|paddleocr|easyocr` explicitly chooses a backend. EasyOCR is an optional legacy backend (`pip install easyocr==1.7.2`), not a default dependency.
- `PIU_OCR_DEVICE=auto` selects the ONNX Runtime CUDA provider when installed and available, otherwise CPU.
- `PIU_OCR_DEVICE=cpu` explicitly forces CPU inference.
- `PIU_OCR_DEVICE=cuda` or `cuda:0` requires a compatible GPU-enabled ONNX Runtime. An unavailable explicitly requested device is an error. `mps` is supported only by the optional EasyOCR backend; native macOS Vision needs no device selection.

Install a compatible GPU-enabled ONNX Runtime for CUDA inference; the default package is CPU-only. OCR identity changes refresh saved text recognition while retaining verified acquisition. Linux and macOS use different models, so host accuracy is validated with representative recordings rather than assumed equivalent. Provision `.local/cache/paddleocr/` before offline operation. The [official model exports](https://huggingface.co/PaddlePaddle) define preprocessing and character dictionaries; [PaddleOCR DB postprocessing](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppocr/postprocess/db_postprocess.py) describes polygon extraction and expansion.

## Full local regeneration

```sh
sh scripts/run.sh .venv/bin/python scripts/regenerate.py --jobs 3
```

This runs the existing `just auto` interface over cached source IDs, without downloading media when each `raw/` directory contains one completed recording. Per-source logs and a report with exit status, elapsed time and before/after source metadata are saved in `.local/regeneration-*/`. Failed sources do not prevent the remaining sources from running. The command exits non-zero if any source failed or changed. Keep concurrency low on GPU hosts to avoid loading multiple model copies into limited VRAM.
