# Visual evidence channels

The analyzer retains four channels on the original recording timeline. The
`visual_channels` object in `analysis.json` and the standalone
`visual-channels.json` expose every retained event, including unassigned and
unresolved observations. Association does not erase or change raw observations.
Stage-result counts remain an additional consistency reference, not an event
source or a quota used to manufacture matches.

| Channel | Native observations | Derived events / units |
| --- | --- | --- |
| `popup` | Combo values/confidence in `frames.jsonl`; word label, confidence, box and blank/unknown state in `judgments.jsonl` | Separate combo changes and word refreshes, with their original display brackets and source PTS |
| `receptors` | Per-lane white fraction and known/unknown light state in `hold-frames.jsonl` | State runs and confirmed off-to-on transitions; persistent light is not repeated input |
| `motion` | Every detected lane/position in `frames.jsonl`; fitted and excluded trajectories in `analysis.json` | Tracks, target estimates and exclusions, including unassigned tracks |
| `processing` | Spatial lane-color, white and visibility masks around receptors in `processing-features.npz` | Per-head persistence samples, bounded disappearance, passage beyond the target, or explicit unresolved state; hold endpoints remain separate |

Each channel has its own counts. These units are not interchangeable. Chords
can share one popup; holds generate repeated HUD updates without repeated
presses. Receptor onset counts require corroboration, rather than counting
every bright frame or candidate transition. Unknown lane frames and processing
failures remain visible in counts and review warnings.

The motion channel also exposes `hold_risk`, a source-bound derivation of every
native near-receptor body cause. The report lists all lanes' cause bounds and
exact image-component owners, including unresolved causes, because a hold in
another lane can make a popup ambiguous. See [hold input risk](hold-input-risk.md)
for the distinction between an approaching body and a possible held state.

Configured [non-playable artwork](object-roles.md) is interpreted between raw
observations and track reconstruction. `object-interpretation.json` links each
separated candidate to its original frame-local detection index and source PTS.
Raw motion and body channel views still expose those candidates; derived note
tracks, cap types, holds and UCS rows use the interpreted view. A role never
supplies an input or judgment event.

## Observing note processing

Tracking expiry is not a processing event. During native hold/receptor pixel
acquisition, retain a small spatial band from 1.6 lane spacings above to 3.6
below the receptor. Store packed binary masks at width 325 with original PTS
and playback time; no FPS conversion or per-frame OCR is performed. Spatial
color support is distinct from the scalar receptor-brightness channel.

For a supported moving head, build a silhouette from at least three actual
clear observations of that same head, at least 1.4 lane spacings below the
receptor. Use retained full-frame width-325 masks, so the template can be learned
below the judgment/COMBO regions even when the small receptor band intersects
them. The complete template window must stay inside the field/source bounds and
outside every documented HUD rectangle. White contamination and implausible
color occupancy reject a reference. Preserve the selected source PTS in each
processing record's `template_evidence`; check all native frame counts and PTS
against the receptor masks. No source decoding or OCR is needed.
If full-frame masks are unavailable, only clear observations inside the retained
1.4-2.8-spacing receptor-band approach can supply the template. A hidden window
never becomes a reference just because there are no other samples.
The majority silhouette contains repeatedly observed colored pixels. Animated
fills can have several shapes whose average does not resemble any actual frame.
Retain additional same-head native shapes only when each has at least three
distinct source-PTS supporters with Dice similarity of at least 0.65, spanning
at least half a lane spacing of observed approach motion. Identical shapes are
deduplicated; stationary repeats and isolated color noise do not supply new
poses. Each pose retains its source PTS and supporting frames. The same rule
applies to clear receptor-band references when full-frame features are absent.

Retain each pose's continuous native-feature anchor and its rounded crop center.
The head's fractional position inside that crop is `anchor - round(anchor)`.
Translate this fractional phase to the predicted frame position before selecting
the floor/ceiling image rows; retain nominal alignment as well. These possible
centers differ by at most one vertical feature pixel from nominal. Horizontal
centers remain fixed by lane geometry. This accounts for integer crop sampling,
not an expanded target-time budget or a change to acquired pixels. The majority
silhouette has no individual source phase and keeps nominal alignment.

Presence can use a qualified shape at one of its possible centers. Absence must
reject every shape at every possible center, with sufficient visible coverage
and no white-effect ambiguity at any center. Record the selected comparison's
vertical offset in feature pixels without changing the predicted head position
or its native timestamp.

Follow the expected location using corroborated peer displacement when available,
or the supported local velocity. This channel depends on motion identity;
it does not consult combo values, judgment words or receptor-onset decisions.

A loss of lane color near a bright effect is not clear absence. For otherwise
absent samples, expand the observed white core by 0.1 lane spacings and measure
its overlap with the approach silhouette. At least 30% possible coverage makes
the sample unknown. This accounts for desaturated bloom beyond the strict
white threshold; a clearly present colored silhouette is retained.

Compare the moving color silhouette with the observed pixels at each native
frame. Dice overlap of at least 0.65 with one qualified shape supports presence;
clear absence requires at most 0.18 with every qualified shape, including the
majority silhouette. Bloom near any shape retains uncertainty. A cropped frame
cannot establish absence if any shape lacks the required visible area or
foreground coverage. Intermediate matches, white effects, HUD overlap, clipping, missing
screen visibility and competing same-lane heads remain unknown. These are
implementation thresholds, not measured engine judgment windows.
HUD checks intersect the actual template window, including its edges; samples
retain the named `occluders`. A known HUD-covered detection gap is separately
accounted in continuity diagnostics and does not create a missing-head warning.
An unobserved processing transition after leaving the HUD can still be unresolved.

A processing candidate requires at least three presence samples followed by
two clear absence samples near the receptor. A short white-effect or partial
shape interval may lie between the last presence and first absence; the
whole interval remains the bracket. It is never narrowed to an assumed
moment inside an occlusion. The bracket is at most 75 ms, confirmation is
within 150 ms, and capture gaps over 50 ms break support. A head observed
again invalidates the earlier disappearance. Two positive observations more
than 0.65 lane spacings above the receptor establish passage instead, provided
they continue upward within a 50 ms capture gap. A sufficiently visible partial
shape can corroborate passage: its score must still be at least 0.65 and both
area and foreground coverage at least 80%. This is positive evidence of continued
visibility, not a disappearance, successful judgment or physical press.
Screen cuts, long flashes, competing heads and unsupported motion remain
unresolved. The raw samples retain scores and unknown reasons for review.

Passage retains its original frame/PTS pair independently of an assigned popup.
If both passing observations occur more than the existing 75 ms review guard
after that refresh, report a processing/refresh conflict with the passage proof.
This is an ordering warning, not a calibrated engine-latency rule. It does not
discard the observed refresh, manufacture a replacement input or assign MISS.
In particular, a hold's popup can coincide with a nearby unprocessed tap; a
short timing fit alone does not establish ownership. Judgment-specific handling
must distinguish successful consumption from failure responses before using
this warning as a hard association veto.

A processing conflict gives the reported timing range `conflicted` status.
Retain the assigned refresh and grade in `conflicted_matches`, but do not present
them as a confirmed input or grade. The original bracket is available with
candidate connections enabled. A conflicted association cannot provide
conditional neighboring-row bounds or review ownership anchors. Resolving the
conflict requires evidence; it never supplies an inferred replacement grade.

`matches` contains only usable associations. Channel annotation partitions the
assignments before downstream recovery, label attachment and ownership/count
derivation. All recovery routes reject the same disputed note/refresh pair,
including an identical bracket from another reader. A different note can still
own that refresh when independently supported. Missing processing observations
cannot silently restore a disputed assignment; changed observations can explicitly
re-evaluate it. Presentation repeats validation before deriving popup ownership
and final coverage.

`association_view_format` versions this interpretation separately from native
features, processing shapes and hold geometry. The replay coordinator refreshes
an older association view, while unchanged observation artifacts remain reusable.
The public cached-play path persists association-only changes even when no
pixel, word or hold artifact changed.

The initial counter/word association stage retains source hypotheses from both
lists in stable chart-time/note order. Its source contract does not change merely
because later processing quarantines an assignment. This boundary preserves
native reader reuse without treating a disputed hypothesis as confirmed input.
Event indices are reader-local: disputed-pair checks also require overlapping
native brackets, so a reindexed event at another time is not blocked by an old ID.

Repeated loss before the receptor can mark a visibility boundary rather than
consumption. Require eight independent heads across at least three lanes,
spanning at least one second, with no inter-event gap over three seconds.
Their last visible centers must be at least 0.65 lane spacings below the
receptor and span at most 0.25 spacings in height. Such losses remain
unresolved with a warning. Retain the original loss bracket and source PTS
separately from processing evidence, along with all contributing note IDs.
This does not identify a gimmick, grant an exception, or relocate the receptor;
the cause still requires review of the source and calibration.

Hold heads, bodies and tails already assigned by connected geometry are not
counted as separate tap consumptions. Their processing record references
hold geometry, source-frame coverage, endpoint ranges and censored ends.
Sustained acceptance still comes from receptor state and HUD corroboration;
a body disappearing does not measure a release or establish its chart end.

## Using the channels

Body masks retain the IDs of their original colored connected components,
before white-border or known-HUD bridging. IDs are local to one native source
frame, lane and feature trace; they are not stable across frames or recordings.
Each body also retains its actual foreground bounding box. Accepted holds and
unresolved body tracks retain every frame's component IDs, bounds, original PTS
and playback time in `native_component_evidence`.

This provenance distinguishes a duplicate interpretation from a candidate that
also includes additional cap/body pixels. It does not establish cap ownership
or suppress unresolved geometry by itself. A time/lane overlap, shared subset
or similarly moving boundary cannot explain extra foreground. Replaying body
rules regenerates this metadata from compatible native masks, without decoding
source media or changing the original frame observations.

`play/channels.py` supplies common receptor access, frame alignment checks,
channel collection and match provenance. `play/processing/` supplies native
spatial measurements and bounded disappearance support. Acquisition and
association contracts are separate; compatible pixels can be reinterpreted
without decoding or OCR. Legacy caches without spatial masks require one
native pixel acquisition pass. All four timelines must agree with the saved
native frame timestamps; a mismatch fails the build instead of silently
joining unrelated samples.

Tap recovery requires a unique note row, an eligible positive HUD refresh,
and an independent lane onset or note-disappearance bracket. Disappearance
can therefore support a tap whose receptor transition is hidden by a flash.
It cannot create a successful input on its own, turn MISS into a press,
consume an aggregate update as one arbitrary note, or assign one refresh to
competing rows. Existing ownership, ordering and 250 ms early / 500 ms late
limits still apply. Candidate generation uses the same channel evidence.

Each projected match exposes `visual_evidence` references such as `motion:12`,
`judgment:4`, `receptor:31` and `processing:12`. Receptor and processing records
retain source PTS; popup endpoints map back to their native frame PTS. A
missing endpoint remains null. A reliable disappearance inconsistent with an
existing match produces a `processing_refresh_conflict` warning. Unresolved
tap processing produces `note_processing_unresolved`, even if HUD evidence
already supplies timing. Explicit chart-region exceptions retain their
existing scope; uncertainty is not silently promoted to success.

The HTML quality panel lists channel counts. Selecting a note shows its
processing status, bracket and supporting event references. A four-row SVG
timeline and scrollable native-frame table show popup values/confidence,
receptor states and white fractions, moving-head positions, processing
scores/unknown reasons, and hold-body candidate bounds in the selected lane.
Choose a window of 0.3, 0.6 or 1.5 seconds on each side of the target. Click a
mark or frame button to seek its recording time; source PTS is displayed
separately. Playback moves a retained cursor without rebuilding observations.
The embedded compact observation arrays share `timeline.frames`; each channel
declares its column names. Processing pixels declare their actual crop width
and height. The UI scales body bounds into the note-analysis crop before
comparing y coordinates, accounting for rounded resize heights. Legacy reports without these arrays hide this view. The sidecar
retains the complete observations for other analyses and tools; presentation
never reacquires pixels or mutates evidence.

## Aggregate tap updates

A separate conservative recovery pass handles a confirmed counter increase of
2-10 within at most 100 ms. Chart-row separation need not fit inside that
refresh bracket: two differently timed notes can be pressed in the same
captured frame. The original aggregate bracket remains the input proxy;
receptor animations do not manufacture per-note switch timestamps.

Recovery requires exactly that many plausible single-tap rows and a separate,
confirmed lane onset for every row. Each onset and note must belong to only
one counter proposal and must not be owned by another matched note. Additional
plausible rows, chords with unverified counting semantics, MISS evidence,
known holds, unresolved body tracks and competing counter proposals prevent
recovery. A counter quota alone never supplies missing observations.

A word already associated with one row retains its own narrower bracket and
grade. Other rows receive the aggregate interval and an unknown grade; the
last displayed word is not copied across the update. Reports identify this
association as `aggregate_counter_with_exclusive_lane_onsets` and retain each
onset's source PTS.

## Judgment animation refreshes

A repeated word can relaunch through several small growth steps. Compare a
continuous run of native word boxes over at most 75 ms, requiring two width
growth steps of at least 3%, total width growth over 10% and area growth over
25%, with consistent horizontal/vertical scale. Unknown reads, capture gaps
over 35 ms and substantial shrinkage break the run. Confirm the relaunched
size with another readable frame; one-frame size glitches remain insufficient.
Keep the entire interval from before the first growth step through detection,
rather than claiming an exact animation onset inside it. Moving notes touching
the word remain a required negative case for the word reader and tracker.

Word recognition and refresh tracking have independent cache dependencies.
A tracker upgrade replays the saved timestamped word observations and rebuilds
associations. It does not require OCR, pixel recognition or video decoding.

After independent lane-onset or processing evidence recovers a counter-owned
row, label association checks the observed word refreshes again. The original
mutually unique synchronized-bracket rules still apply, including competing
unassigned words/counters and existing ownership. Only one row (possibly a
chord) with a single counter increment is eligible. This label-only step never
moves notes or changes input brackets. A persistent readable word without a
measured refresh does not supply this evidence; separate post-counter frame
proof still requires its usual multiple distinct source frames.

## Note type evidence and contradictions

A failed hold reconstruction does not establish a tap. The `note_types`
channel retains per-frame `tap`, `hold` or `unknown` observations, original
source PTS, playback time, measured position and source trajectory identity.
It reuses the retained spatial masks, independently of HUD/input decisions.
The native appearance cache (`appearance-features.npz`) retains packed color,
relaxed-color, white, visibility and valid-pixel masks around each original
head detection across its entire approach, at the original analysis resolution.
The acquisition contract includes original detection positions and native PTS;
refits and type-rule changes reuse these pixels. Older receptor-band caches
cannot establish a cap hidden by the HUD there, so a first native appearance
pass is required for those recordings. It performs no OCR and never modifies
source media or the saved native detection timeline.

Only actual tracked positions away from the receptor, HUD and screen edges are
eligible. Match source observations by native time, lane and position, never
by predicted proximity alone. The cap outline must match the native head size
and contain lane color. The visible colored rim outside an inner white outline
belongs to the same cap: measure its connected envelope before checking gaps.
An envelope taller than a normal cap or multiple distinct cap centers cannot
prove a tap. Both margins require valid, color-free and white-effect-free
pixels; black background is valid separation when the foreground cap is visible.
Padded image boundaries are not valid pixels. A connected colored component over
1.6 spacings high with strong vertical support supplies hold evidence. Registered
native caps attached to a strong extended body also supply per-frame hold proof,
including candidates too brief for multi-frame reconstruction. Lack of a connector
alone is insufficient. Other samples remain unknown.

Projection combines evidence by the existing trajectory/hold identities, never
by time proximity alone. A single valid observation of each kind produces
`note_type_conflict`; repeated observations cannot vote away the contradiction.

A cap whose own shape is obscured can inherit hold-kind evidence from a
uniquely connected cap in the same native frame. The retained connection must
already have at least eight connected frames over 120 ms, at least 80% support,
no observed gap, and unique ownership in both directions. Every connection PTS
must map to a real frame with both native positions. At least one endpoint must
have direct complete-cap/extended-body hold evidence at that exact PTS, with no
contradictory tap observation. An unknown cap or an inferred type cannot seed propagation. Preserve the anchor
observation, connection PTS and original unknown/tap observations. This is one
topology step without feedback: a clear tap still creates a conflict, while
failed endpoint times and pending hold geometry remain warnings. It supplies
neither a chart time nor an input event.

Reconstructed hold geometry also supplies hold evidence, with its source-frame
range retained. An isolated cap after that hold has reached the receptor is a
possible processing remnant, not tap evidence; retain its observed appearance
but interpret its type as unknown. Unclassified heads and observed holds without resolved chart
geometry produce `note_type_unresolved`. Complete geometry, physical input
acceptance and note kind are separate conclusions.

Reports mark uncertain types with `?` and conflicts with `!`, retain the chart
geometry for review, and provide original-frame links for type observations.
Only an explicit human-authored check exception matching the warning,
`note_type_conflict` or `note_type_unresolved`, and containing the whole evidence
interval suppresses it. A transformation exception does not hide unknown types. Timing exclusions and other check
exceptions do not suppress type warnings. Suppressed evidence remains in
`recognition-warnings.json` under `chart_exceptions`; no exception is generated
automatically from a contradiction.

Within a complete aggregate counter increment, another constituent row is not
competing counter evidence against an independently recognized word refresh.
A word may label its uniquely associated constituent row while all rows retain
the original aggregate timing bracket. Each label still requires its own
observed refresh; the final visible grade is never copied to the other rows.
Words outside that counter group and incomplete/invalid bursts retain the
normal conflict checks.

A single native-frame counter value can split an otherwise confirmed short
aggregate burst when its neighboring values are independently stabilized.
Every intermediate integer must actually be observed with independent digit
recognition confidence of at least 0.9, in monotone order. Contextual or weak
reads, missing states, backward glitches, bursts over 100 ms and confirmation
delays over 75 ms retain the original aggregate. Each resulting bracket uses
the last actual previous-value frame and the first actual next-value frame,
with original source PTS. No times are interpolated and no judgment grade is
inherited. A true configured +10 without intermediate observations remains +10.

Splitting a burst preserves the uniquely aligned row domains of the original
counter sequence. Unaffected counter events retain their original unique row
identities; refined constituents still have to satisfy their tighter native
brackets, ordering and ambiguity checks. Newly available events cannot steal
an unrelated anchored row just because the dynamic-programming score changes.

## Layer boundaries and replay

The original recording is the source layer. PTS and recording playback time
remain unchanged. Cached masks are measurements derived from that source;
they are not lossless RGB frames and cannot establish features discarded by
the acquisition thresholds.

| Layer | Artifacts | May depend on |
| --- | --- | --- |
| Pixel features | `native-features/`, `processing-features.npz`, `appearance-features.npz`, judgment feature cache | Source identity, original timestamps, crop geometry and declared measurement thresholds |
| Frame observations | `frames.base.jsonl`, `frames.jsonl`, `judgments.jsonl`, `hold-frames.jsonl` | Pixel features and recognition/detection rules |
| Channel interpretations | Receptor state runs, trajectories, persistence events, note types and hold geometry | Frame observations and explicit geometric rules |
| Associations | Chart targets, popup ownership, inferred input brackets, policies and warnings | Channel interpretations, timing reference and chart metadata |
| Presentation | HTML, SVG and compact observation tables | Saved evidence and associations |

`visual-channels.json` is an aggregate view spanning these layers, rather than
an acquisition artifact. Its `layers` manifest identifies artifact ownership,
channel dependencies and interpretation limits. Existing per-channel arrays
remain available to reports and other consumers.

The popup view exposes the baseline combo value/confidence, current read mode
and contextual-recovery flag alongside the current recognition. The baseline
is the original pre-refinement recognition, not a ground-truth counter or a
context-free pixel read. Baseline and current traces must have identical PTS.
Receptor fractions are measurements; common-flash filtering and onset runs
are interpretations. Neither is a measured physical switch state.

Persistence inspection uses a registered native displacement path or a bounded,
locally verified native trajectory. The chosen `motion_basis` is retained.
It does not require accepted UCS placement or successful shared chart timing.
Consequently an excluded chart note may still have visible disappearance
support. Such support does not restore its chart target, remove its timing
warning, or by itself create a successful input association. Unsupported local
motion remains explicitly unresolved; no rejected target is silently accepted.

New body/receptor acquisition retains full-crop threshold planes in compressed
128-frame chunks under `native-features/`, independently of the body detector.
Body-rule changes replay these planes without decoding, while receptor-band
masks carry their own pixel contract. Compatible legacy receptor-band masks
remain usable despite an unrelated body-detector revision. Legacy body caches
without full-crop planes require one acquisition pass when their detector
changes. Changing source geometry or measurement thresholds can still require
reading the original recording. All caches remain ignored generated data.

Configured zero-speed intervals are a projection over retained native evidence.
A `scroll_pause` model removes paused duration from the displacement clock,
requires compatible stationary samples and both moving flanks, then rechecks
the retained receptor-band masks using that path. The source PTS, failed chart
targets and measured popup/input intervals are unchanged. This projection does
not replace the acquisition sidecar. Explained stationary records remain
inspectable alongside their original motion warnings; unsupported motion and
unrelated recognition failures still warn.

## A clipped confirmation after clear disappearance

A fast note can have one fully visible clear-absence frame after its last visible
head, followed by a comparison window slightly outside the image. Cropping the
real intersection can corroborate that first absence when at least 80% of both
the window area and the expected colored foreground remain observable. Never
pad unseen pixels as background or move the expected center to fit the image.
Retain the visible area/foreground fractions and original confirmation PTS.

A partial window supplies confirmation only. It cannot establish the first clear
absence, a last-present sample or a passed-receptor conclusion. At least three
full present observations and one full clear absence are still required. Keep
all existing color-overlap, white-core/bloom, HUD, competing-head, source-cadence
and receptor-position checks. Low coverage, loss of the foreground, black/cut
frames, flashes or truncated recording cannot confirm absence. The reported
transition stays bounded by the last full presence and first full clear absence;
the later partial observation never narrows that range. This is processing
information, not proof of a successful grade or a physical switch press.
A strong partial match that may show the head still present refutes the proposed
disappearance instead of being counted as absence or silently ignored. Keep it
as `partial_head_present`; further absence cannot confirm an earlier transition
across that possible reappearance.
