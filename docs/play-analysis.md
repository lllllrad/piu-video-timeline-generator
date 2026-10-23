# Visual play timing analysis

Run metadata analysis once, then opt into native-frame play analysis:

```sh
just auto VIDEO
just play VIDEO --segment 1
```

`--segment` selects a 1-based entry in the saved `analysis.json` segment list, and defaults to 1. This does not download media or rerun metadata recognition. A matching play result is reused without frame decoding or OCR; `--force` rebuilds it. Completed output is preserved if a new build fails.

Open `.local/data/SOURCE_ID/play/segment-001/report.html` locally. The report embeds its data and uses no external scripts, fonts or services. It includes:

- the original recording, with seek links from the charts and event table;
- reconstructed visible note-head crossing times by lane;
- combo update brackets and their timing offsets;
- coverage, unreadable digits, excluded trajectories and ambiguous events;
- a receptor/combo overlay and an editable, downloadable layout;
- display-latency correction and relative median centering.

If the browser cannot read the relative media path, select the original file in the page. Playback depends on browser codec/container support. The tool never transcodes, trims, retimes or overwrites that recording. The page does not upload selected files.

## Meaning of the measurements

This reconstructs visible supported-color note heads from the recording. It does not load an authoritative chart or recover unseen notes, beat positions or hold durations.

For each usable note track, a local linear fit predicts when its center crosses the observed receptor row. A confirmed combo change is bracketed between the last frame with the old counter and the first frame with the new counter. Two observations must confirm each counter value. Matching uses those time intervals, never fabricated subframe input timestamps.

The default association tolerance is 45 ms around the observed update interval. Only unique single-note/single-increment associations are accepted. Chords, holds, rolls, resets, counter jumps, frame gaps and competing associations remain excluded. A long colored component reaching the receptor region blocks timing matches in its interval (with a 100 ms guard), because hold ticks and dense overlapping stacks cannot be attributed safely. A reset is not proof of a missed note. Sparse results indicate limited visual evidence, not a lack of player inputs.

The raw offset contains input/render/display latency. It is not a measured physical switch time, hardware latency or game judgment-window score. A positive externally calibrated delay is subtracted with:

```sh
just play VIDEO --segment 1 --display-delay-ms 30
```

The HTML slider changes the displayed offsets only; changing associations requires rerunning the command. Median centering is relative alignment, not hardware calibration.

## Variable speed and uncertain motion

The tracker does not assume one scroll speed for the song. It fits at most the last twelve observations of each head, compares earlier/later slopes, checks residuals and limits extrapolation to 160 ms. Nonlinear, stopped/reverse, distant and insufficient tracks are excluded. A sufficiently linear portion after a speed change may still be usable. There is no attempt to reconstruct arbitrary gimmicks, disappearing notes or unsupported skins.

## Geometry and limited windows

The current visual detector supports the usual blue diagonal, red diagonal and yellow center note colors, with white outlines and five or ten ordered receptor columns. Auto-calibration looks for repeated receptor outlines in the source-verified STAGE evidence frame. A different skin, unusual composition or simultaneous players needs a reviewed layout.

For a smaller review window, `--start` is an absolute local playback time and `--duration` limits the analysis window inside that gameplay interval:

```sh
just play VIDEO --segment 1 --start 48 --duration 12
just play VIDEO --segment 1 --layout layout.json --player p2
```

A layout uses game-relative fractions:

```json
{
  "receptor_y": 0.142,
  "note_y_max": 0.95,
  "combo_roi": [0.43, 0.52, 0.14, 0.075],
  "lanes": [
    {"x": 0.38, "color": "blue", "name": "DL"},
    {"x": 0.44, "color": "red", "name": "UL"},
    {"x": 0.50, "color": "yellow", "name": "C"},
    {"x": 0.56, "color": "red", "name": "UR"},
    {"x": 0.62, "color": "blue", "name": "DR"}
  ]
}
```

Do not use the example as calibration for an arbitrary recording. Inspect the overlay and the digit-template source frames. Simultaneous players must be analyzed separately with an explicit player and a verified layout; no values are combined across sides.

## Cost, timestamps and evidence

At most 32 small counter crops receive English OCR to learn digit templates. A digit needs examples from distinct source timestamps; repeated glyphs or resized variants from one source do not count as independent confirmation. Native gameplay frames then use color components, visual tracking and digit-template comparisons, without neural OCR on each frame. Unknown glyphs remain unreadable.

FFmpeg streams frames without an FPS filter. Original integer PTS and filter time base determine source time, including nonzero container origins. Resizing is only for analysis; it does not alter media time. `--width` controls analysis resolution (default 650 pixels). Note tracking has no dependency on metadata OCR sampling rate.

Outputs stay under the ignored `.local/` directory:

- `analysis.json`: tracks, crossing estimates, combo brackets, matches and exclusions;
- `frames.jsonl`: native source PTS, playback time, note detections and counter observations per frame;
- `layout.json`, `preview.png`: geometry and its original source image;
- `evidence/`: digit-template training images, OCR observations and exact source timestamps;
- `report.html`: local interactive presentation.

Changing source metadata, play bounds, geometry, resolution, player, song/chart or association correction invalidates the play cache. This feature is experimental: verify representative frames and report coverage before drawing conclusions about a player.
