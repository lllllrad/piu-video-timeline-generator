# Visual play timing analysis

The independent [gameplay visual model](gameplay-visual-model.md) defines what receptors, heads, bodies, tails and display changes mean, how their geometry relates, and what video evidence can establish. This document describes the implementation and its operating limits.

Run metadata analysis once, then opt into native-frame play analysis:

```sh
just auto VIDEO
just play VIDEO --segment 1
just play VIDEO --all
```

`--segment` selects a 1-based entry in the saved `analysis.json` segment list, and defaults to 1.
This does not download media or rerun metadata recognition. A matching play result is reused without
frame decoding or OCR; `--force` rebuilds it. Completed output is preserved if a new build fails.
`--all` analyzes every saved metadata segment and writes a linked `play/index.html` overview,
continuing past individual failures and reporting them at the end. It cannot be combined with
`--start` or `--duration`.

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

This reconstructs visible supported-color note heads from the recording. It does not load an authoritative chart or recover unseen notes or beat positions. Visible long-note bodies can supply start/end ranges; obscured or unreliable endpoints remain unresolved.

Interrupted same-lane head fragments can be joined across at most 350 ms when the predecessor and successor are unique and their combined track passes the motion and receptor-proximity checks. Prediction uses corroborated shared screen displacement when available, otherwise a local linear path. Competing continuations, other lanes and inconsistent positions stay separate. Joined notes retain their source fragment indices and all original time/position observations.

For a head entering the HUD, the intact approach below the overlay supplies the
reappearance prediction. Shifted partial centers inside the HUD cannot override
that path. At least four intact observations spanning 60 ms are required; the
reappearance must be within 650 ms of the last intact point and agree at its
first three observations. Unique predecessor/successor ownership and the combined
motion checks still apply. Original partial observations remain in the trace.

For each usable note track, observed motion predicts when its center crosses the receptor row. A confirmed combo change is bracketed between the last frame with the old counter and the first frame with the new counter. Two observations must confirm each counter value. Judgment words are observed independently of the counter, including before combo 4 and after a combo break. Input matching uses those observed intervals, never invented subframe press timestamps.

Shared displacement requires at least three one-to-one head correspondences across at least two
lanes. Ambiguous displacement and gaps in independent support break the motion history. This history
lets a head reconnect through a HUD occlusion even when short per-head source-time velocity
estimates disagree because captured game images repeat. A corroborated head uses one screen pixel
per shared displacement pixel; a measured slope inconsistent with that model is refused. Full
unclipped observations estimate its position robustly, preserving the relative spacing of
simultaneously visible notes.

Stable shared runs use one affine time mapping; otherwise a validated nearby mapping or fractional
interpolation between original source frames is used. Target estimates are not rounded to frame
numbers or snapped to beat quotas. Tests distinguish equal relative pixel spacing from unknown
absolute capture latency. Source-frame cadence, measured clock residual and displacement uncertainty
remain in the target range. True speed changes that fail the clock checks do not borrow a constant
song speed. A head last observed inside the HUD may use up to 650 ms / six lane spacings of
independently observed shared motion; other heads retain the normal proximity bound. With
insufficient shared evidence, the original local fit and explicit exclusions remain.

`scroll_motion` records the original-time displacement history and supporting lane counts. Per-note `fit_method`, `motion_target_phase`, clock model and original crossing-frame PTS explain the estimate. Saved native detections can be refitted without decoding gameplay frames or running OCR; these models never retime the recording.

The default association tolerance is 45 ms around the observed update interval. A monotone sequence
alignment compares rows and counter updates in time order, so close successive notes do not all get
discarded merely because their search windows overlap. Near-equal competing alignments remain
excluded. The counter advances per judged row, not per head: a multi-head chord shares one increment
and one observed bracket. If a counter jump spans multiple consecutive rows, every associated row
retains the original aggregate bracket; individual timestamps are never invented. The row span must
fit inside the observed bracket plus 20 ms of fitting tolerance. Unassigned updates remain visible
in a separate evidence table. Rolls, resets and observation gaps remain excluded from discrete input
matching. Long notes are modeled separately as sustained states. Implausible large jumps and
high-valued backwards digit reads do not replace the stable counter baseline. A long colored
component reaching the receptor region blocks timing matches in its interval (with a 100 ms guard),
because hold ticks and dense overlapping stacks cannot be attributed safely. A reset is not proof of
a missed note. Sparse results indicate limited visual evidence, not a lack of player inputs.

The report separates reconstructed note heads, heads with timing evidence, and matched counter refreshes. It also reuses confirmed result-panel judgments as a whole-song reference when available, without extra OCR. Judgments include hold ticks, so their total is not a note-head count or a coverage percentage. A short analysis window still shows the whole-song reference. Missing matches are analysis gaps, not evidence of absent inputs.

## Excluded visible detections

The report and command output warn when visible detections are excluded from the reconstructed chart
without an explicit chart-region exception. `excluded-trajectories.json` lists their original
visible time spans, lanes and reasons, including short uncertain/noise tracks. The warning panel
appears above playback and provides source-video seek buttons. A duplicate owned by a retained note
or a fragment represented by a reconstructed hold is accounted for separately. A general region
annotation does not suppress warnings: an explicit timing-processing/check exception must contain
the whole observed trajectory when no trustworthy target exists. Partly overlapping exceptions leave
the warning visible.

`recognition-warnings.json` additionally lists unresolved hold endpoints, rejected
body geometry, uncertain component ownership, ambiguous or absent timing evidence,
and matched refreshes whose judgment label remains unknown. These items appear in
the same warning panel and command output. A hold component is accounted for only
with repeated source-frame cap or connected-body evidence. Duplicate ownership
requires matching same-lane positions at shared source times; a nearby target time
alone is insufficient. Partial body tracks can be accounted for by a uniquely
matching, repeatedly observed cap identity. All supporting observations remain in
the evidence. An unresolved end stays unknown even when the body disappears.

Word-template matching includes the shrinking part of the judgment animation
(0.7-1.4 times a sampled template in the partial-word channel). A touching note
can corrupt the connected-component bounds at those sizes too. Shape coverage,
agreement across word sections and the margin against competing labels remain
required; a readable persistent label alone does not establish a new refresh.
Corroborated label reads are retained for every eligible single-row counter
update, including updates whose tap ownership is initially unresolved. If hold
projection later recovers that row using independent lane evidence, it reuses
the same label proof and original frame timestamps. Aggregate counter jumps and
conflicting or insufficient reads remain unlabeled.

An obscured receptor sample is unknown. It cannot veto a review candidate as an
inactive lane, and it cannot establish a confirmed lane onset. Candidates that
overlap unknown samples retain that distinction in `lane_receptor_status` and
remain unresolved without independent ownership evidence. Known inactive lanes
still reject candidates; unknown intervals elsewhere do not excuse them.

## Long notes and sustained recognition

When enough extended-body frames identify the upper cap, they determine head
identity before isolated cap frames are considered. An isolated trailing cap
can share the same body track before the connector is visible or after it
shrinks; those frames alone cannot distinguish head from tail. Contradictory
extended-body observations remain unresolved.
Original-color and white-border candidates keep separate body tracks, so a
short augmented cap cannot replace a long body's continuation at a HUD cut.

Short white-border candidates are checked against the original per-lane color
trace across the entire shared cap approach, including frames without a body
candidate. Native cap identities must agree in at least two body samples; the
gap test then needs at least eight clear source frames spanning 120 ms, stable
cap separation within 1.5 feature pixels, and a missing vertical color column
in at least 80% of the samples. Three adjacent image rows measure continuity.
Strong support uses the body detector's color thresholds and a column width
of at least 0.12 lane spacings (minimum two pixels); absence uses a relaxed
saturation >60/value >90 mask so a dim or thin possible stem remains unknown.
Samples at the receptor, clipped field boundary or HUD are excluded. This
check can refute an apparent short hold; it does not by itself confirm a hold
or an input. A refuted candidate is accounted for only when both original tap
heads remain represented. The trace and its original PTS remain in JSON.

Endpoint corroboration runs before rejecting a short body with unreadable local fits: independently
tracked heads and tails can resolve it. Strong body stripes require geometric corroboration. A
weaker stripe (at least 72% colored support in five extended-body observations spanning 80 ms)
additionally requires both a tracked head following the upper edge and a tracked tail following the
lower edge. Missing or displaced arrows cannot qualify through time proximity alone. `body_evidence`
distinguishes `strong_stripe` from `stripe_and_tracked_edges` in the saved hold reconstruction.

A directly linked tail retains its native crossing range. Body-to-cap positional tolerance establishes the association and does not widen that measured range; doing so could consume a real subsequent tap. A body-only endpoint still includes uncertainty from the approximate cap offset and local fit.

Head selection first compares native trajectories against the body's visible upper edge at matching source times. A clipped box's extrapolated start cannot override a corroborated upper cap merely because it lies closer to the tail's timestamp. Distinct candidates with residuals less than one body-analysis pixel apart remain unresolved. Time proximity is a fallback only when there are insufficient overlapping observations, not when observed positions contradict the proposed head.

Connected-color features preserve gaps between tap caps. Only two extended
stripes with shared pixel columns can bridge a gap inside a declared HUD region;
ragged column endpoints use their actual colored pixels. HUD-cut boundaries are
not caps. Native head trajectories register the stripe's cap centers at matching
source times, requiring at least four agreeing observations and 80% ownership
agreement. Other detections are suppressed as body fragments only with repeated
geometric containment evidence; uncertain ownership remains visible and warned.

Hold recognition has its own `input.association_window`. For a directly tracked tail, its trailing
search margin is 0.55 lane spacings divided by the measured cap velocity, bounded before a
separately observed next same-lane tap. This is a visual response association tolerance, not chart
target uncertainty or a measured release. Within an independently established hold's certain
interior, a lane-local dim pulse plus a positive HUD refresh can supply support even when that
frame's body box is missing. The derived hold cache depends on both native note geometry and
combo/judgment events, so changed HUD evidence recomputes recognition while reusing body/receptor
pixels.

Dim, brief receptor pulses can support an already reconstructed hold when all three observations
agree: a rise of at least 0.16 above the lane's recent baseline, light above the other lanes, and a
connected body at the receptor. A positive combo or PERFECT/GREAT/GOOD/BAD update must occur within
40 ms. Such context can retain a single native frame; shared flashes, static light, MISS and missing
bodies cannot. Each recovered span records the corroborating update indices/ranges and original
source PTS. This hold-only evidence does not relax tap onset detection or invent a press/release
time.

A long note is one body from its head to its tail. Holding the panel is sufficient during that body;
repeated combo or judgment ticks are not separate presses. The analyzer acquires small native-frame
color/body and receptor features once, without OCR, preserving every saved source PTS. Narrow
colored vertical stripes distinguish bodies from separated tap heads. Body approaches and tails are
fitted locally. A saved arrow track corroborates the body's lower edge when at least four
overlapping native observations agree, with at least 65% within the positional tolerance while the
body is extended. This geometric tail association also applies to holds shorter than 120 ms and
takes precedence over body-box endpoint extrapolation, using the arrow's motion-based target range.
A nearby separate tap outside that connected edge remains a tap. Repeated fragments sharing a head
or tail are deduplicated. Unsupported motion or clipped endpoints remain explicitly censored.

The chart shows a long body in its lane color with a square start note and end cap. A question mark
identifies an unresolved endpoint, rather than an invented target or release time. Magenta spans
beside it show a filled receptor within the reconstructed hold interval. Receptor observations come
from every native frame, including neighboring frames where a flash or overlay hides the body's
color; a body box is not required in the same frame as recognition. Only directly supported
recognition spans are drawn. The overall recognition envelope is retained in JSON for audit and is
not rendered as a dashed range; gaps are not measured switch transitions. This is visual evidence of
hold recognition, not a physical pedal sensor. A player may already be holding before the head, and
may keep holding after the tail. Physical press and release times therefore stay `null`.

Hold heads and tail fragments are removed from the discrete-press view. Counter or word updates during an ongoing hold cannot establish a new tap merely because their times are close: another lane needs its own receptor onset to support a separate tap candidate. Existing native detections and tap associations remain preserved in analysis for audit, with a separate `hold_analysis` reconstruction. The HTML projects them into a hold-aware chart and does not count hold ticks as independent presses.

`hold-frames.jsonl` preserves per-frame body measurements, source PTS, per-lane receptor states and
native white-area fractions. Fractions allow receptor interpretation to change without reacquiring
pixels. Saved traces containing only boolean receptor states receive a single native receptor-strip
top-up in `receptor-features.npz`, independently keyed by source, bounds, geometry, measurement
encoding and original timestamp digest; this pass performs no OCR. Shared full-grid whitening and
its decay are unknown input evidence, rather than simultaneous presses on empty lanes. Strong light
above the shared baseline can remain lane-local evidence. An unknown interval cannot establish a
fresh independent input onset. `hold-features.json` identifies the source, bounds, ROI, geometry and
detector format. `holds.json` records reconstructed long notes, covered fragments, endpoint ranges
and sustained recognition spans. Changing geometry/source/detector encoding reacquires these
features; changing hold reconstruction reuses them. Metadata OCR, counter templates and word
templates are reused. Missing or incompatible pixel features require a small-frame decode pass;
matching saved features are reused without decoding.

## Judgment words without a visible counter

PERFECT, GREAT, GOOD, BAD and MISS use a separate native-frame region. An optional `judgment_roi`
layout field overrides the automatically derived region; the default includes the expanded initial
word animation. At most 24 representative word crops receive English OCR, balanced across observed
text colors. Exact vocabulary repeated across distinct source timestamps can corroborate stylized
low-confidence text. Learned word shapes and colors are then matched by normalized contours, without
per-frame OCR. When a touching note corrupts the word component, a bounded search compares the word
itself at several animation scales. At least three of four horizontal word regions must retain their
letter shapes; a small fragment or solid matching color cannot establish a label. Font templates are
reusable across unchanged source media. Unknown words remain unknown, and the report lists unlearned
labels.

A new label, reappearance after a confirmed blank, or a sudden proportional scale restart can establish a refresh. Two source frames confirm it. A persistent PERFECT is not counted repeatedly; unreadable/occluded frames are not assumed blank. Scale restarts require adjacent visible observations, consistent geometry and confirmation. Onsets with more than 100 ms of observation uncertainty remain unscored.

Mutually unique overlapping counter/word refresh brackets are paired first. Confirmed pairs anchor
the remaining monotone alignment, preventing neighboring judgments from shifting onto an already
assigned row. Counter and word order must agree. Remaining judgment rows are aligned between these
anchors and merged with counter evidence. One note is counted once, with `combo`, `combo+judgment`
or `judgment` provenance. Competing counter evidence and hold/dense-stack intervals remain excluded.
MISS is observed failure evidence, never a press timestamp or timing-offset sample. A unique
unmatched visible row in a bounded preceding window may be listed as a possible miss; dense
ambiguous cases retain only the observed MISS event.

An already matched single-row counter update can also receive a label from at least two consistent,
high-confidence word observations within 50 ms after its first new frame. Two agreeing reads must be
no more than 35 ms apart. Unreadable later frames do not invalidate already confirmed letters or
vote against a label. The window stops before the next observed counter transition; conflicting
words, MISS, sparse observations and aggregate increments remain unlabeled. This supplies a label
only: it does not create a word refresh or narrow the original timing interval. These matches retain
the contributing source PTS in `judgment_observations`, use `judgment_label_source:
post_combo_frames`, and have no `judgment_event`. The HTML marks them as `word frames` and
explicitly shows `Judgment unknown` for unresolved labels. Compatible saved word observations are
reused without decoding or OCR.

`judgments.jsonl` retains word observations, confidence, bounding boxes and original source PTS.
`evidence/judgments/` contains sampled crops, OCR provenance, font templates and compressed native
color features. Word detection/refresh changes can reuse those features and existing fonts without
decoding or OCR; cached word classifications are invalidated when the reader changes. This path
analyzes the current recording without creating or requiring a persistent chart catalog. The HTML
shows the judgment and evidence source for matched heads, plus all observed word refreshes,
including unassigned and MISS evidence.

## Comparing target and input ranges

See [reviewing play timing reports](play-report.md) for the synchronized video/chart
controls, interval markers and note comparison table.

## Variable speed and uncertain motion

The tracker does not assume one scroll speed for the song. It excludes bounding-box centers clipped
near the receptor, then fits at most the last twelve unclipped observations of each head. It
compares earlier/later slopes with pixel-rounding and measured slope-error tolerance, checks
residuals and limits extrapolation to 250 ms and 2.5 lane spacings. Repeated rendered game frames
are retained with their original native timestamps; stepwise motion contributes to uncertainty
rather than automatically being called acceleration. Predictions bridge gaps up to 120 ms, or 350 ms
for established tracks entering the judgment/combo overlay. If the whole fit fails, a sufficiently
long linear span after that occlusion may establish a crossing. Same-lane crossing estimates within
35 ms are treated as duplicate colored head fragments; excluded duplicates remain in the evidence.
Nonlinear, stopped/reverse, distant and insufficient tracks are excluded. A sufficiently linear
portion after a speed change may still be usable. There is no attempt to reconstruct arbitrary
gimmicks, disappearing notes or unsupported skins.

## Geometry and limited windows

Standard full-game captures use fixed Phoenix receptor profiles for Single-left, Single-right and
Double. The chart label establishes the lane count and a recognized participant side or `--player`
chooses the Single profile. Flashes and touching receptor borders therefore do not block
acquisition. `layout.method` is `fixed_phoenix_game_layout`, and the profile/revision are saved as
declared geometry. Existing native observations retain their original geometry. An explicit
`--layout` takes precedence. Unknown mode/side uses the visual calibration fallback described below.

The current visual detector supports the usual blue diagonal, red diagonal and yellow center note
colors, with white outlines and five or ten ordered receptor columns. Whole-head white contours
locate centers and color verifies the lane, avoiding fragmented internal colored rings.
Auto-calibration compares receptor outlines across source frames. A previously validated layout from
the same source can be reused only when at least four current outlines span half its lane grid and
match its positions. Complementary partial outlines can establish a grid only when every receiver is
directly observed at distinct source timestamps and the complete geometry is unambiguous. If sparse
samples repeatedly hit beat flashes, a bounded 800 ms native-frame window supplies differently
phased observations before the temporal-median fallback. No missing lane is filled in from presumed
spacing. Remaining flashes can be removed using a temporal median of calibration frames. Unknown
chart labels do not force five lanes. A different skin, unusual composition or simultaneous players
needs a reviewed layout.

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

At most 32 small counter crops receive English OCR to learn digit templates. Subsequent plays can
reuse a saved font bank from unchanged source media and inspect up to eight samples, running OCR
only on samples the bank cannot read. A complete font from another local recording can also be
imported after at least six current crops covering six digit classes match at confidence 0.9 or
higher and improve on the local reader by at least three crops. Only glyph images and training
provenance transfer; counter values and native timestamps always come from the current recording.
Contradictory neural-OCR labels cannot overwrite strongly recognized glyphs. Weak saved readers can
be revalidated against saved bootstrap crops without OCR; their exact native counter pixels are
replayed, with original note observations and the original counter baseline preserved. The imported
bank is preserved independently; neither counter values nor timing events are transferred between
plays. Confirmed counter values can supply additional native-resolution font examples. A recent
stable value can restrict visually supported candidates, but blank/unsegmented crops remain
unreadable. Temporal-template reads are marked in the frame trace. The initial native pass retains
losslessly compressed RGB counter crops with original source PTS and playback times. A bounded
recovery pass reuses these pixels, trying brighter white thresholds where the original read failed.
Older analyses without this pixel cache decode the counter strip once and retain it for future font
updates; incompatible source/region contracts or corrupted arrays fail explicitly. A
recovered value must lie between the nearest original counter readings, within a nondecreasing gap
of at most 250 ms and ten increments. Existing readable values, note detections and source PTS are
preserved. `frames.base.jsonl` retains the observations before recovery; accepted additions have
`combo_recovered: true`. A digit needs examples from distinct source timestamps; repeated glyphs or
resized variants from one source do not count as independent confirmation. Native gameplay frames
then use color components, visual tracking and digit-template comparisons, without neural OCR on
each frame. Unknown glyphs remain unreadable.

FFmpeg streams frames without an FPS filter. Original integer PTS and filter time base determine source time, including nonzero container origins. Resizing is only for analysis; it does not alter media time. `--width` controls analysis resolution (default 650 pixels). Note tracking has no dependency on metadata OCR sampling rate.

Outputs stay under the ignored `.local/` directory:

- `analysis.json`: native tracks, crossing estimates, combo brackets, matches, exclusions and the separate `hold_analysis` reconstruction;
- `frames.jsonl`: native source PTS, playback time, note detections and counter observations per frame;
- `counter-pixels.npz`: exact RGB counter crops and original timestamps for recovery and font updates without another video pass;
- `layout.json`, `preview.png`: geometry and its original source image;
- `calibration/`: additional source frames and a temporal median when needed;
- `evidence/`: digit-template training images, font-bank archives, OCR observations and exact source timestamps;
- `report.html`: local interactive presentation;
- `holds.json`, `hold-features.json`, `hold-frames.jsonl`: long-note reconstruction and reusable native pixel observations;
- `timing-ranges.json`: disposable per-note target ranges, matched brackets, alternative refreshes, conditional bounds and unresolved reasons. It is derived from saved analysis without OCR or frame decoding.
- `recognition-warnings.json`: unresolved recognition items, scoped chart exceptions and independently accounted hold fragments.

Changing source metadata, play bounds, geometry, resolution, player or song/chart invalidates the
observation cache. Compatible saved native observations can be refitted after a tracking/association
change or latency-correction change without decoding or OCR. A counter-reader upgrade may decode
only the small counter region and must match every saved source PTS; force a complete rebuild with
`--force`. This feature is experimental: verify representative frames and report coverage before
drawing conclusions about a player.

## Cache compatibility

Cache reuse also checks saved counter bootstrap crops against newly available local font banks. An incomplete reader can be invalidated by a newly available font only after the same broad pixel-validation requirements pass. The check does not mutate the cache or decode media. A successful replacement rereads only the native counter strip; note observations and source timestamps stay unchanged. A complete, locally validated reader does not depend on unrelated new recordings.

Sparse bootstrap crops can reuse a font already broadly pixel-validated in another play of the exact same media identity, game ROI and analysis width. This requires two newly matching crops covering five digit classes at confidence 0.9 or higher and at least two more strong reads than the weak local reader. Changed recordings or geometry still require broad validation. A sparse within-recording import cannot qualify as the broad donor for another sparse import.

Lane onset support retains an explicit bracket from the last observed unlit receptor to the first
sustained lane-local light. A common screen flash may obscure the intermediate samples for at most
150 ms, provided adjacent native observations remain within 75 ms. The bracket retains both original
source PTS. Unknown samples remain unknown; persistent light, an unknown initial state, unrelated
unreadable samples and gaps in decoded observations cannot establish a new onset. This support can
corroborate an independently observed display refresh; it does not measure a physical switch or turn
a hold tick into a press.

One lane transition cannot independently confirm multiple repeated taps. If several matched notes on that lane claim the same onset bracket, their hold-time associations remain ambiguous unless each has a separate unclaimed transition. Neighboring display refreshes remain available as review candidates.

A one-frame observed onset can be corroborated by another lit sample after a bounded common flash (at most 150 ms, with continuous native observations). The unknown frames remain unknown and the later light does not create another onset. The earlier onset retains its original bracket and the corroborating sample's original PTS.

A second association pass can recover an unassigned tap when a narrow positive combo/word refresh
identifies one row and that lane has one independent, sustained receptor onset. It retains the
original display bracket and onset source PTS. Existing event ownership, processed-row order, the
hard early/late window and local display-offset consistency still apply. Competing same-lane heads
within the local association tolerance, disjoint refresh alternatives, shared onsets, MISS,
aggregate jumps and observation gaps cannot be promoted. Chord heads may share one row only when
each recovered lane has its own onset. This pass consumes cached observations and does not use
generated chart drafts or stage-grade quotas as evidence.

Strict counter-to-row alignments that overlap a possible hold/dense interval are retained as deferred matches. A separate lane-local onset can restore a tap association after hold geometry is known. Recovery requires a single counter increment, a visible tap rather than a hold component, an unshared onset and no conflicting matched row at the same refresh. The original counter bracket is preserved. Aggregate jumps and sustained receptor light remain insufficient to recover a press.

Cache compatibility is checked by artifact format and dependencies, not by a list of analyzer
releases. Pixel features record their encoding and source/ROI/time/width identity in
`evidence/judgments/features.json`. Font files declare their binary-mask format. Reader output
records the feature identity, font-content fingerprint and reader revision; associations
additionally depend on notes, counter evidence, unsupported intervals, display correction and
association revision. Changing association logic reuses saved word observations. Changing the reader
reuses compatible pixel features and fonts. Source or feature-format changes reacquire pixels.

Feature/font files without format tags are validated and normalized at the load boundary. Unknown
formats are rejected. Native note traces are validated for normalized coordinates and original
timestamps. Song spelling and level corrections update report metadata without reacquiring the same
gameplay frames; a changed single/double layout requires compatible lane geometry. If metadata
inserts a play and renumbers later reports, immutable retained snapshots are matched by original
media, playback interval, ROI, width, player and layout. Copied evidence paths are relocated into
the new report directory.

## Shared visual evidence

[Visual channels](visual-channels.md) describes independently retained popup,
receptor-effect, moving-note and processing observations. `visual-channels.json`
provides counts, unassigned events, unresolved samples and source-timestamped
references for reuse outside the HTML report. Native spatial processing masks
are cached in `processing-features.npz`; compatible association changes do not
require decoding or OCR.

Head coordinate registration precedes beat reconstruction. `head-registration.json`
records per-identity native silhouette offsets, qualified source-frame observations,
uncertainty and conflicts. `analysis.json` retains `detected_points` for calibrated
tracks alongside derived `points`; the raw frame traces are unchanged. Stable
pixel calibrations are fitted into the shared motion model before reassociating
independently observed combo/judgment events. Compatible native appearance masks
are reused without decoding or OCR. Changing registration rules invalidates derived
timing, not native acquisition.

The head-registration artifact also retains independent cap-template references,
supporting head identities and original PTS. Compatible connected caps may use
these references to measure coordinates without treating the body's bounding box
as the cap. Templates are learned from directly measured isolated caps once per
segment and never from their own inferred matches. Low-similarity and ambiguous
matches do not supply an offset; existing geometry/type warnings remain. Native
NPZ arrays are loaded once for this pass rather than decompressed per sample.

Processing samples may include `template_coverage` (visible area and expected
foreground fractions) and `confirmation_only` when a comparison window is partly
outside the pixel band. Such a sample can corroborate an earlier full clear
absence, never establish its timestamp. Confirmed events expose
`confirmation_partial_template` alongside the original confirmation PTS. Strong
partial presence remains `partial_head_present` and blocks an earlier proposed
disappearance. This processing evidence does not change chart coordinates or
create a physical press, release or grade.

## Independent beat coordinate checks

Beat verification can instead establish a rhythm-to-coordinate relation from
other calibrated heads in the same fitted native block. Freeze native support
before trying phases; never feed a newly rescued pair back into its references.
Each reference needs at least four calibrated, field-visible source observations
spanning 65 ms, with native coordinate errors at most 1.5 pixels. Exclude the two
heads being checked. Require at least five other candidate heads, two lanes,
three distinct target times and 300 ms of target span, within 750 ms of the
tested targets. Their candidate beat times must explain every reference offset
within one pixel; a robust estimate does not permit discarding outliers.

Use this relation only to interpolate a pair's beat separation inside the
reference target range, with at least four actual co-observations over 65 ms
inside the original gap-check window. The candidate pair also needs calibrated
native support. Select models by those support requirements, independently of
whether their prediction passes. Every eligible block must satisfy the original
pixel-gap tolerance; do not average a conflicting prediction away. A missing
independent model leaves the existing clock-based check in force. Unverified
caps, wrong rows and nonlinear references do not acquire a convenient scale.
This check uses no input, combo, judgment, result totals or existing chart notes.
`beat-timing.json` retains successful and failed `coordinate_checks`, including
reference identities, source PTS ranges, native residuals and candidate times.
It verifies spacing, not absolute phase; bounded audio alignment and native
target intervals remain separate requirements.
