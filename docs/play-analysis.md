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
- a vertical lane chart with earlier notes above later notes, showing target and input ranges;
- a note-by-note comparison table, including unmatched targets, and two aligned range bars for the selected note;
- combo and judgment-word refresh brackets, their evidence source and timing offsets;
- coverage, unreadable digits, excluded trajectories and ambiguous events;
- a receptor/combo overlay and an editable, downloadable layout;
- display-latency correction and relative median centering.

If the browser cannot read the relative media path, select the original file in the page. Playback depends on browser codec/container support. The tool never transcodes, trims, retimes or overwrites that recording. The page does not upload selected files.

## Meaning of the measurements

This reconstructs visible supported-color note heads from the recording. It does not load an authoritative chart or recover unseen notes, beat positions or hold durations.

For each usable note track, a local linear fit predicts when its center crosses the observed receptor row. A confirmed combo change is bracketed between the last frame with the old counter and the first frame with the new counter. Two observations must confirm each counter value. Judgment words are observed independently of the counter, including before combo 4 and after a combo break. Matching uses those time intervals, never fabricated subframe input timestamps.

The default association tolerance is 45 ms around the observed update interval. A monotone sequence alignment compares rows and counter updates in time order, so close successive notes do not all get discarded merely because their search windows overlap. Near-equal competing alignments remain excluded. The counter advances per judged row, not per head: a multi-head chord shares one increment and one observed bracket. If a counter jump spans multiple consecutive rows, every associated row retains the original aggregate bracket; individual timestamps are never invented. The row span must fit inside the observed bracket plus 20 ms of fitting tolerance. Unassigned updates remain visible in a separate evidence table. Holds, rolls, resets and observation gaps remain excluded. Implausible large jumps and high-valued backwards digit reads do not replace the stable counter baseline. A long colored component reaching the receptor region blocks timing matches in its interval (with a 100 ms guard), because hold ticks and dense overlapping stacks cannot be attributed safely. A reset is not proof of a missed note. Sparse results indicate limited visual evidence, not a lack of player inputs.

The report separates reconstructed note heads, heads with timing evidence, and matched counter refreshes. It also reuses confirmed result-panel judgments as a whole-song reference when available, without extra OCR. Judgments include hold ticks, so their total is not a note-head count or a coverage percentage. A short analysis window still shows the whole-song reference. Missing matches are analysis gaps, not evidence of absent inputs.

## Judgment words without a visible counter

PERFECT, GREAT, GOOD, BAD and MISS use a separate native-frame region. An optional `judgment_roi` layout field overrides the automatically derived region; the default includes the expanded initial word animation. At most 24 representative word crops receive English OCR, balanced across observed text colors. Exact vocabulary repeated across distinct source timestamps can corroborate stylized low-confidence text. Learned word shapes and colors are then matched by normalized contours, without per-frame OCR. When a touching note corrupts the word component, a bounded search compares the word itself at several animation scales. At least three of four horizontal word regions must retain their letter shapes; a small fragment or solid matching color cannot establish a label. Font templates are reusable across unchanged source media. Unknown words remain unknown, and the report lists unlearned labels.

A new label, reappearance after a confirmed blank, or a sudden proportional scale restart can establish a refresh. Two source frames confirm it. A persistent PERFECT is not counted repeatedly; unreadable/occluded frames are not assumed blank. Scale restarts require adjacent visible observations, consistent geometry and confirmation. Onsets with more than 100 ms of observation uncertainty remain unscored.

Mutually unique overlapping counter/word refresh brackets are paired first. Confirmed pairs anchor the remaining monotone alignment, preventing neighboring judgments from shifting onto an already assigned row. Counter and word order must agree. Remaining judgment rows are aligned between these anchors and merged with counter evidence. One note is counted once, with `combo`, `combo+judgment` or `judgment` provenance. Competing counter evidence and hold/dense-stack intervals remain excluded. MISS is observed failure evidence, never a press timestamp or timing-offset sample. A unique unmatched visible row in a bounded preceding window may be listed as a possible miss; dense ambiguous cases retain only the observed MISS event.

An already matched single-row counter update can also receive a label from at least two consistent, high-confidence word observations within 50 ms after its first new frame. Two agreeing reads must be no more than 35 ms apart. Unreadable later frames do not invalidate already confirmed letters or vote against a label. The window stops before the next observed counter transition; conflicting words, MISS, sparse observations and aggregate increments remain unlabeled. This supplies a label only: it does not create a word refresh or narrow the original timing interval. These matches retain the contributing source PTS in `judgment_observations`, use `judgment_label_source: post_combo_frames`, and have no `judgment_event`. The HTML marks them as `word frames` and explicitly shows `Judgment unknown` for unresolved labels. Compatible saved word observations are reused without decoding or OCR.

`judgments.jsonl` retains word observations, confidence, bounding boxes and original source PTS. `evidence/judgments/` contains sampled crops, OCR provenance, font templates and compressed native color features. Word detection/refresh changes can reuse those features and existing fonts without decoding or OCR; cached word classifications are invalidated when the reader changes. This path analyzes the current recording without creating or requiring a persistent chart catalog. The HTML shows the judgment and evidence source for matched heads, plus all observed word refreshes, including unassigned and MISS evidence.

## Comparing target and input ranges

The **Vertical note chart** keeps lanes in their original left-to-right order and places time from top to bottom. Colored arrows locate fitted note targets; blue bands show target uncertainty, and amber outlines show corrected input ranges at the same lane position. An input above its target is earlier and one below is later. A connector makes the displacement visible; overlapping bands retain their uncertainty. Chords line up across lanes, and the selected target has a white outline. Gray crosses enabled by the exclusion control show only track endpoints.

The green horizontal line follows video playback. Use the recording-position slider to scrub, **Previous note / Next note** to inspect supported heads including unmatched ones, and **Window** to change time scale. **Chart height** adjusts the vertical view from 360 to 20,000 pixels; increasing it spreads notes and timing ranges apart without changing the time window or measurement values. Windows as short as ±0.1 seconds provide further vertical magnification. Arrow sizes and range widths follow the lane width rather than a fixed small glyph size. Click a target or input outline to select its note and seek the recording. The initial view opens at the first matched target (or first supported target when none match). A five-lane chart and a ten-lane chart use the same left-to-right layout without combining players.

Select a note in the **Note timing comparison** table or lane chart to see its two ranges on the same axis. The target range is the fitted receptor crossing plus/minus its saved prediction uncertainty. The input estimate is the matched combo/judgment observation bracket with the selected display-delay correction subtracted. The table uses absolute recording positions; the selected-note plot uses milliseconds relative to the fitted crossing. Changing the correction updates input ranges, difference intervals and plots together, without moving the target or changing associations.

The difference includes uncertainty on both sides: for target `[T_low, T_high]` and corrected input `[I_low, I_high]`, it is `[I_low − T_high, I_high − T_low]`. A wholly negative interval establishes an earlier estimate, a wholly positive interval a later estimate, and overlap with zero leaves that distinction unresolved. These are measurement uncertainty ranges, not game judgment windows. This also applies to the overview's offset bars.

Every supported target appears even without a matched refresh; its input remains **Unconfirmed**. Possible MISS candidates never receive press times. Shared chord and aggregate row brackets retain their original evidence without inventing individual switch times. Excluded trajectories remain available through the chart's exclusion control and evidence JSON, without fabricated target ranges. No tracked chart catalog is required: original chart-file timestamps are still unavailable, and input estimates remain display-based rather than measured physical switch times.

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

At most 32 small counter crops receive English OCR to learn digit templates. Subsequent plays can reuse a saved font bank from unchanged source media and inspect up to eight samples, running OCR only on samples the bank cannot read. The imported bank is preserved independently; neither counter values nor timing events are transferred between plays. Confirmed counter values can supply additional native-resolution font examples. A recent stable value can restrict visually supported candidates, but blank/unsegmented crops remain unreadable. Temporal-template reads are marked in the frame trace. A bounded recovery pass decodes only the small counter region, trying brighter white thresholds where the original read failed. A recovered value must lie between the nearest original counter readings, within a nondecreasing gap of at most 250 ms and ten increments. Existing readable values, note detections and source PTS are preserved. `frames.base.jsonl` retains the observations before recovery; accepted additions have `combo_recovered: true`. A digit needs examples from distinct source timestamps; repeated glyphs or resized variants from one source do not count as independent confirmation. Native gameplay frames then use color components, visual tracking and digit-template comparisons, without neural OCR on each frame. Unknown glyphs remain unreadable.

FFmpeg streams frames without an FPS filter. Original integer PTS and filter time base determine source time, including nonzero container origins. Resizing is only for analysis; it does not alter media time. `--width` controls analysis resolution (default 650 pixels). Note tracking has no dependency on metadata OCR sampling rate.

Outputs stay under the ignored `.local/` directory:

- `analysis.json`: tracks, crossing estimates, combo brackets, matches and exclusions;
- `frames.jsonl`: native source PTS, playback time, note detections and counter observations per frame;
- `layout.json`, `preview.png`: geometry and its original source image;
- `calibration/`: additional source frames and a temporal median when needed;
- `evidence/`: digit-template training images, font-bank archives, OCR observations and exact source timestamps;
- `report.html`: local interactive presentation.

Changing source metadata, play bounds, geometry, resolution, player or song/chart invalidates the observation cache. Compatible saved native observations can be refitted after a tracking/association change or latency-correction change without decoding or OCR. A counter-reader upgrade may decode only the small counter region and must match every saved source PTS; force a complete rebuild with `--force`. This feature is experimental: verify representative frames and report coverage before drawing conclusions about a player.

## Cache compatibility

Cache compatibility is checked by artifact format and dependencies, not by a list of analyzer releases. Pixel features record their encoding and source/ROI/time/width identity in `evidence/judgments/features.json`. Font files declare their binary-mask format. Reader output records the feature identity, font-content fingerprint and reader revision; associations additionally depend on notes, counter evidence, unsupported intervals, display correction and association revision. Changing association logic reuses saved word observations. Changing the reader reuses compatible pixel features and fonts. Source or feature-format changes reacquire pixels.

Untagged legacy feature/font files are validated and normalized at the load boundary. Unknown formats are rejected. Native note traces are validated for normalized coordinates and original timestamps. Song spelling and level corrections update report metadata without reacquiring the same gameplay frames; a changed single/double layout requires compatible lane geometry. If metadata inserts a play and renumbers later reports, immutable retained snapshots are matched by original media, playback interval, ROI, width, player and layout. Copied evidence paths are relocated into the new report directory.
