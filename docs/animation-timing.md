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
separate shape references; a selected note-image bank alone does not calibrate
the receptor effect.

Gold-effect contour measurements remain under visual review. The exploratory
warm/white threshold and post-effect background subtraction have not established
an isolated effect boundary: fading pixels can leave the threshold mask without
any geometric contraction, and notes, stationary outlines or neighboring effects
can join its connected component. Area changes from those masks do not validate
a decay curve or an animation-age estimator. Earlier phase-bin agreement and
error measurements are not recognition accuracy and must not enable inference.

Compare original enlarged frames with every proposed contour before measuring
size. Identify the same visible structure across frames: central artwork, thin
rays and diffuse bloom need separate definitions. Reject contaminated or clipped
regions and retain ambiguous boundaries. Later frames used as a background must
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
