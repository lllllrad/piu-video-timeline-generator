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

## Observing note processing

Tracking expiry is not a processing event. During native hold/receptor pixel
acquisition, retain a small spatial band from 1.6 lane spacings above to 3.6
below the receptor. Store packed binary masks at width 325 with original PTS
and playback time; no FPS conversion or per-frame OCR is performed. Spatial
color support is distinct from the scalar receptor-brightness channel.

For a supported moving head, build a silhouette from at least three actual
approach observations between 1.4 and 2.8 lane spacings below the receptor.
The majority silhouette contains repeatedly observed colored pixels. Follow
its expected location using corroborated peer displacement when available,
or the supported local velocity. This channel depends on motion identity;
it does not consult combo values, judgment words or receptor-onset decisions.

A loss of lane color near a bright effect is not clear absence. For otherwise
absent samples, expand the observed white core by 0.1 lane spacings and measure
its overlap with the approach silhouette. At least 30% possible coverage makes
the sample unknown. This accounts for desaturated bloom beyond the strict
white threshold; a clearly present colored silhouette is retained.

Compare the moving color silhouette with the observed pixels at each native
frame. Dice overlap of at least 0.65 supports presence; at most 0.18 supports
absence. Intermediate matches, white effects, HUD overlap, clipping, missing
screen visibility and competing same-lane heads remain unknown. These are
implementation thresholds, not measured engine judgment windows.

A processing candidate requires at least three presence samples followed by
two clear absence samples near the receptor. A short white-effect or partial
shape interval may lie between the last presence and first absence; the
whole interval remains the bracket. It is never narrowed to an assumed
moment inside an occlusion. The bracket is at most 75 ms, confirmation is
within 150 ms, and capture gaps over 50 ms break support. A head observed
again invalidates the earlier disappearance. At least two clear observations
more than 0.65 lane spacings above the receptor establish passage instead.
Screen cuts, long flashes, competing heads and unsupported motion remain
unresolved. The raw samples retain scores and unknown reasons for review.

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

`play/channels.py` supplies common receptor access, frame alignment checks,
channel collection and match provenance. `play/processing.py` supplies native
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
