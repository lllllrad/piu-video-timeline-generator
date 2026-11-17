# Judgment and receptor animation timing

## Judgment and receptor animation timing

Repeated judgments can restart the size animation without changing the displayed
word or passing through a blank frame. Reviewed PERFECT sequences show a return
to a larger word followed by shrinkage toward a stable size. A subsequent refresh
can interrupt that sequence and restart it. A stable word therefore does not
identify the age of the most recent judgment, and an unchanged label does not
establish that no refresh occurred. These observations do not establish the same
animation curve for every grade, font or game version.

Distinguish a visible size reset from small changes in a reader's bounding box.
Moving notes can touch the letters, and component and partial-template readers
can report different bounds for the same visible word. Apparent growth caused by
that change is not an animation restart. Compare the letters in the original
frames, retain the read mode and confidence, and corroborate the new size in
subsequent frames. The inspected sequences establish large-to-small settling;
they do not establish a universally observable small-to-large launch phase or a
linear scale-to-elapsed-time law.

Receptor effects likewise have several changing structures: a bright core,
colored bloom and narrow rays can evolve separately. The stationary outline,
approaching notes, background and neighboring effects can enter the same box.
Brightness-threshold bounds can grow, shrink or remain unchanged at different
animation ages; changing the threshold changes the measured contour. A clipped
crop can also conceal expansion. A radius, area or bounding-box width alone is
not a validated animation clock. Different visible effect styles require
separate shape references bound to the active note skin and effect revision.
Existing cap/body images do not supply missing effect references or phase timing.

Gold-effect contour measurements remain under visual review. The exploratory
warm/white threshold and post-effect background subtraction have not established
an isolated effect boundary: fading pixels can leave the threshold mask without
any geometric contraction, and notes, stationary outlines or neighboring effects
can join its connected component. Area changes from those masks do not validate
a decay curve or an animation-age estimator. Earlier phase-bin agreement and
error measurements are not recognition accuracy and must not enable inference.

Compare original enlarged frames with every proposed contour before measuring
size. Identify the same visible structure across frames: central artwork, thin
rays and diffuse bloom need separate definitions. Mask only positively established
occluded or clipped regions, retain the remaining visible support, and preserve
ambiguous boundaries. Overlap is an expected acquisition condition, not a reason
to discard an entire frame or event. Later frames used as a background must
actually show the relevant lane without its effect, with compatible background
content. An absent body detection is not proof of an isolated tap. Visible
rebrightening during a connected hold does not establish a new physical press.

For timing, retain the original source-frame bracket around a corroborated
change. Repeated captured images do not supply new animation phases. Missing or
unreadable frames widen the bracket. A word refresh, receptor-effect onset and
physical switch transition are separate events; their order or delay must not be
assumed from visual proximity. Hold ticks can refresh a word while an effect is
already lit, without another physical press.

Before using animation phase to narrow a timestamp, validate a model separately
for the declared word/effect style and recording geometry. Inspect isolated
events through launch, settling and decay, then test repeated refreshes, sustained
holds, other lanes/grades, overlays and capture repeats. Keep reader boxes and
measured contours separate from phase estimates. Fit on one set of events and
measure timing errors on other events against independently observed onset
brackets, retaining ambiguous phases and failures. Estimating physical switch
time additionally needs independent display-latency calibration. The current
bounded review supports restart detection, not calibrated subframe timing from
size. See [the stored channels and implementation policy](visual-channels.md#animation-measurement-and-timing-limits).

## Skin-specific localization with overlap

The intended timing evidence is a sequence of localized effect structures, not
the bounding box of every connected bright pixel. Bind effect references to the
selected skin/revision, direction, render geometry and phase convention. A gold
effect and a gray receptor's illumination need different appearance models;
their different outlines are expected, not detector failures by themselves.
Keep uncertain skin/phase alternatives explicit instead of mixing their shapes.

For each original frame, localize the reference's anchor and positively observed
landmarks in game-crop coordinates. Preserve the distinction between the fixed
receptor origin and moving/expanding structures inside the effect. Measure phase
from those structures' positions, scale, shape and brightness history. Neither a
whole-component centroid nor an assumed receptor center replaces an observed
effect position. A stationary effect can still supply appearance-phase evidence;
an unchanged origin alone does not identify its age.

Use independently observed moving-head/body geometry, neighboring effect
hypotheses and foreground overlays to describe which comparison pixels are
unavailable. An overlap hypothesis is not a proven layer order: mixed pixels
with unknown composition remain unknown. Do not subtract a predicted note as if
its original pixels were observed, fill a hidden ray, or use target/input success
to choose a convenient segmentation. If several origins or phases fit the
visible support, retain all of them. Missing geometry cannot certify absence of
an occluder. Visible compatible parts remain useful even when another part is
obscured; complete occlusion cannot supply a new measured position.

Retain at least these fields separately from inferred input associations:

| Frame evidence | Required meaning |
| --- | --- |
| Original frame identity and PTS/playback time | Exact source timeline; no phase snapping or retiming |
| Skin/effect reference and phase candidates | Actual content binding and unresolved appearance alternatives |
| Origin, landmark coordinates and coordinate bounds | Observed spatial evidence in declared game-crop/reference coordinates |
| Compared, occluded and unknown regions | Visible support plus the observed owner/reason of each excluded region |
| Shape/brightness residuals and competing fits | Evidence for localization, not a success score selected by later timing |
| Instance/reset alternatives | Temporal continuity versus a possible new rendered effect |

Only independently supported phase-age ranges may map frame positions to an
effect-onset range. Across a continuing instance, compatible frame constraints
can narrow that range; conflicting frames must retain competing instances or a
failure instead of forcing an intersection. Repeated captures, plateaus and
occluded landmarks limit the gain in precision. Preserve the frame measurements
when changing phase or display-delay models. Effect-onset constraints can then
corroborate existing note-processing and popup timing; conversion to physical
switch time still needs its separately validated delay model.

The 300-window contour audit demonstrates limitations of its generic threshold
extractor. It does not establish that overlapping frames or different skins are
unusable for timing. Its crop/brightness flags are review context, not automatic
whole-case exclusions or recognition-accuracy labels. A successor needs to test
skin-specific localization on visible support and report timing performance
separately for clear, partially occluded, ambiguous and fully hidden frames.

## Animation measurement and timing limits

`judgments.jsonl` retains native word boxes, labels, confidence, read mode when
available, playback times and source PTS. Boxes are reader measurements in the
judgment crop, not independently segmented glyph contours. Partial-template
dimensions come from a discrete template bank; changes between templates or
reader modes must not be treated as continuous scale measurements. The current
tracker uses corroborated growth to detect a refresh and preserves an observed
time bracket. It does not fit the complete grow/shrink/decay curve or invert word
size into elapsed animation time.

Receptor white fractions measure occupancy of fixed lane-local regions.
`hold-frames.jsonl` and `receptor-features.npz` do not store an effect radius,
segmented contour or calibrated animation age. Retained spatial masks may support
exploratory contour measurements under their declared thresholds, but discarded
color/intensity detail requires the original recording. Independent observation
capture still declares `input_effects: not_measured`; mask capture is not a
completed effect-animation measurement.

The [visual model](gameplay-visual-model.md#judgment-and-receptor-animation-timing)
separates observed resets from reader artifacts and specifies validation needed
before phase-based timing. No new animation-phase or physical-switch timestamps
are produced by documenting these observations. The growth thresholds below are
current detection policy, not measured universal animation constants.

Effect contour extraction and phase inference are not implemented in the
production analyzer. Future observations need the original PTS, lane, geometry,
explicit contour/brightness definition, background reference when used,
clipping/overlap state and full uncertainty. Normalization using an event's
later peak or background is retrospective. Validate the segmentation against
original images before evaluating timing on independent events.

## Judgment animation refreshes

Aligned combo and word refreshes may share a timing family, but retain their
own row capacities. A counter increment of two does not turn a single word
refresh into a two-row observation. Count plausible alternatives separately for
each source's own bracket and distance: a single word with two plausible rows
remains ambiguous even beside an aggregate counter. A word can independently
support a tap during a hold only with the existing unique-row and lane-onset or
processing proof; the aggregate counter is not consumed as a single tap.

A repeated word can relaunch through several small growth steps. Compare a
continuous run of native word boxes over at most 75 ms, requiring two width
growth steps of at least 3%, total width growth over 10% and area growth over
25%, with consistent horizontal/vertical scale. Unknown reads, capture gaps
over 35 ms and substantial shrinkage break the run. Confirm the relaunched
size with another readable frame; one-frame size glitches remain insufficient.
Keep the entire interval from before the first growth step through detection,
rather than claiming an exact animation onset inside it. Moving notes touching
the word remain a required negative case for the word reader and tracker.

A clear blank run spanning at least 100 ms remains evidence after subsequent
unknown frames. Returning to the same word can therefore establish reappearance
without a label change or size growth. Clear samples must be no more than 50 ms
apart to complete that run; unknown or missing frames cannot complete it. Retain
the witnessed `blank_observation_range` on the event and bracket reappearance
from the last clear read through the first returning word. A resulting bracket
over 100 ms remains excluded as `judgment_observation_gap`; the unknown interval
is never removed from its uncertainty. Readable return consumes the blank proof,
so a persistent word cannot repeatedly create events.

Word recognition and refresh tracking have independent cache dependencies.
A tracker upgrade replays the saved timestamped word observations and rebuilds
associations. It does not require OCR, pixel recognition or video decoding.

A delayed counter read retains its entire native observation bracket. A narrower
word refresh inside that bracket can establish synchronization even when their
upper endpoints differ by more than 25 ms, provided each bracket overlaps only
that one eligible refresh on the other channel and the relation preserves event
order. A counter-owned row cannot take an already owned word or a word whose
timing also fits another visible row. Independent lane-supported associations
remain separate evidence. The existing 100 ms counter and 50 ms word span limits still apply.
Competing overlaps do not supply this additional proof. Original brackets remain
unchanged; synchronization cannot turn a wide counter bracket into a precise
input timestamp. Acquisition and word-recognition caches remain reusable when
this association rule changes.

After independent lane-onset or processing evidence recovers a counter-owned
row, label association checks the observed word refreshes again. The original
mutually unique synchronized-bracket rules still apply, including competing
unassigned words/counters and existing ownership. Only one row (possibly a
chord) with a single counter increment is eligible. This label-only step never
moves notes or changes input brackets. A persistent readable word without a
measured refresh does not supply this evidence; separate post-counter frame
proof still requires its usual multiple distinct source frames.

A synchronized counter/word pair may already belong to part of a visible chord.
The remaining heads can share it only when every compatible head has the exact
same reconstructed target and a distinct lane, every head is a confirmed tap
with restored bounded timing, and no hold risk, alternative refresh, competing
row or processing contradiction remains. Existing owners must belong to that
same row and already own both channels. A nearby stagger is a different row.
Retain original target uncertainty and both display brackets; this completes
row ownership without asserting a separately observed lane onset. The reported
row size includes existing and newly connected heads, including when word
recovery establishes the pair in a later association generation.

An already assigned neighboring row can stop competing for another refresh
only when its separate synchronized counter/word pair has an exclusive lane
onset or independently observed disappearance. Original PTS must validate that
physical bracket. At least four co-observed positions over 65 ms in fitted
native coordinate blocks must separate the rows beyond both positional errors.
Source-bound image measurements must jointly exclude zero separation; missing
or conflicting coordinate bounds do not establish a different row.
Observed height order must agree with target and disjoint display order.
Unknown types, shared onsets, missing source frames and hold risk keep the
competition unresolved. `fixed_refresh_rows` retains the conditional ownership,
physical bracket and native separation samples; source timing bounds, display
brackets and prior associations remain unchanged.

Known hold caps retain native appearance samples without becoming separate
presses. [Hold cap coverage](hold-cap-coverage.md) describes their bounded use
in corroborating an otherwise missing image region.

## Reusable RGB reference experiments

The [effect reference extraction tool](effect-reference-extraction.md) now saves
original-PTS RGB crops and conservative note/body exclusion envelopes, then models
candidate reference sequences in TypeScript. It excludes insufficiently visible,
saturated or high-error comparisons and retains rejected evidence for review.
These candidate banks are not installed in the production timing analyzer.
