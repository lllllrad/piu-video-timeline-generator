# Visual play timing analysis

Run metadata analysis once, then opt into native-frame play analysis:

```sh
just auto VIDEO
just play VIDEO --segment 1
just play VIDEO --all
```

`--segment` selects a 1-based entry in the saved `analysis.json` segment list, and defaults to 1. This does not download media or rerun metadata recognition. A matching play result is reused without frame decoding or OCR; `--force` rebuilds it. Completed output is preserved if a new build fails. `--all` analyzes every saved metadata segment and writes a linked `play/index.html` overview, continuing past individual failures and reporting them at the end. It cannot be combined with `--start` or `--duration`.

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

The default association tolerance is 45 ms around the observed update interval. A monotone sequence alignment compares rows and counter updates in time order, so close successive notes do not all get discarded merely because their search windows overlap. Near-equal competing alignments remain excluded. The counter advances per judged row, not per head: a multi-head chord shares one increment and one observed bracket. If a counter jump spans multiple consecutive rows, every associated row retains the original aggregate bracket; individual timestamps are never invented. The row span must fit inside the observed bracket plus 20 ms of fitting tolerance. Unassigned updates remain visible in a separate evidence table. Holds, rolls, resets and observation gaps remain excluded. Implausible large jumps and high-valued backwards digit reads do not replace the stable counter baseline. A long colored component reaching the receptor region blocks timing matches in its interval (with a 100 ms guard), because hold ticks and dense overlapping stacks cannot be attributed safely. A reset is not proof of a missed note. Sparse results indicate limited visual evidence, not a lack of player inputs.

The report separates reconstructed note heads, heads with timing evidence, and matched counter refreshes. It also reuses confirmed result-panel judgments as a whole-song reference when available, without extra OCR. Judgments include hold ticks, so their total is not a note-head count or a coverage percentage. A short analysis window still shows the whole-song reference. Missing matches are analysis gaps, not evidence of absent inputs.

The raw offset contains input/render/display latency. It is not a measured physical switch time, hardware latency or game judgment-window score. A positive externally calibrated delay is subtracted with:

```sh
just play VIDEO --segment 1 --display-delay-ms 30
```

The HTML slider changes the displayed offsets only; changing associations requires rerunning the command. Median centering is relative alignment, not hardware calibration.

## Variable speed and uncertain motion

The tracker does not assume one scroll speed for the song. It excludes bounding-box centers clipped near the receptor, then fits at most the last twelve unclipped observations of each head. It compares earlier/later slopes with pixel-rounding and measured slope-error tolerance, checks residuals and limits extrapolation to 250 ms and 2.5 lane spacings. Repeated rendered game frames are retained with their original native timestamps; stepwise motion contributes to uncertainty rather than automatically being called acceleration. Predictions bridge gaps up to 120 ms, or 350 ms for established tracks entering the judgment/combo overlay. If the whole fit fails, a sufficiently long linear span after that occlusion may establish a crossing. Same-lane crossing estimates within 35 ms are treated as duplicate colored head fragments; excluded duplicates remain in the evidence. Nonlinear, stopped/reverse, distant and insufficient tracks are excluded. A sufficiently linear portion after a speed change may still be usable. There is no attempt to reconstruct arbitrary gimmicks, disappearing notes or unsupported skins.

## Geometry and limited windows

The current visual detector supports the usual blue diagonal, red diagonal and yellow center note colors, with white outlines and five or ten ordered receptor columns. Whole-head white contours locate centers and color verifies the lane, avoiding fragmented internal colored rings. Auto-calibration compares receptor outlines across source frames. A previously validated layout from the same source can be reused only when at least four current outlines span half its lane grid and match its positions. Remaining flashes can be removed using a temporal median of calibration frames. Unknown chart labels do not force five lanes. A different skin, unusual composition or simultaneous players needs a reviewed layout.

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

At most 32 small counter crops receive English OCR to learn digit templates. Subsequent plays can reuse a saved font bank from unchanged source media and inspect up to eight samples, running OCR only on samples the bank cannot read. The imported bank is preserved independently; neither counter values nor timing events are transferred between plays. Confirmed counter values can supply additional native-resolution font examples. A recent stable value can restrict visually supported candidates, but blank/unsegmented crops remain unreadable. Temporal-template reads are marked in the frame trace. A digit needs examples from distinct source timestamps; repeated glyphs or resized variants from one source do not count as independent confirmation. Native gameplay frames then use color components, visual tracking and digit-template comparisons, without neural OCR on each frame. Unknown glyphs remain unreadable.

FFmpeg streams frames without an FPS filter. Original integer PTS and filter time base determine source time, including nonzero container origins. Resizing is only for analysis; it does not alter media time. `--width` controls analysis resolution (default 650 pixels). Note tracking has no dependency on metadata OCR sampling rate.

Outputs stay under the ignored `.local/` directory:

- `analysis.json`: tracks, crossing estimates, combo brackets, matches and exclusions;
- `frames.jsonl`: native source PTS, playback time, note detections and counter observations per frame;
- `layout.json`, `preview.png`: geometry and its original source image;
- `calibration/`: additional source frames and a temporal median when needed;
- `evidence/`: digit-template training images, font-bank archives, OCR observations and exact source timestamps;
- `report.html`: local interactive presentation.

Changing source metadata, play bounds, geometry, resolution, player or song/chart invalidates the observation cache. Compatible saved native observations can be refitted after a tracking/association change or latency-correction change without decoding or OCR; force a complete rebuild with `--force`. This feature is experimental: verify representative frames and report coverage before drawing conclusions about a player.
