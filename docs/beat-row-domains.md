# Native chord constraints on beat row domains

Two candidate beat rows must not be selected by proximity alone. Sometimes one
cap has a broad target interval while another cap at the same observed height
has a unique row. Their measured concurrency can intersect the row domains
without widening either time interval or changing the natural subdivision.

## Measurement requirements

Use canonical centers actually measured in each source frame, never the fallback
offset positions. Both caps must be in different lanes, with at least four common
measurements spanning 65 ms. Every common measurement must put them within one
analysis pixel; do not discard a disagreeing frame to create a chord. Source PTS
must agree at the same playback time; an inconsistent cache fails explicitly.
Each cap's declared coordinate uncertainty must be at most one analysis pixel.

The mean observed trajectory must move upwards at least 0.8 lane spacings and
fit a line with maximum residual at most 1.5 pixels. Its conservative speed
lower bound subtracts two pixels of endpoint uncertainty from the observed
displacement before dividing by the source-time span. Stationary, nonlinear,
insufficiently measured and unregistered candidates cannot supply this proof.

## Resolving a domain

For each proposed natural Split, multiply its row duration by the measured speed
lower bound. Equality is usable only if that minimum row distance exceeds three
pixels: one pixel of observed pair separation plus one pixel of uncertainty for
each cap. Otherwise distinct rows cannot be distinguished at this resolution,
and the observation does not constrain their domains.

Intersect the integer row domains of all connected equality constraints. Every
member must retain exactly one row. Two shared alternatives remain ambiguous;
an empty intersection refutes that subdivision. A finer natural subdivision
may explain a previously incompatible coarse grid, but cannot be used to choose
between unresolved alternatives. Ordinary time intervals and common song-phase
requirements remain unchanged. No grades, counter increments, input onsets,
existing chart note rows or result-count quotas supply these constraints.

Recompute these constraints for every bounded song-phase candidate and score it
with the same native-spacing and concurrency checks used for the final result.
Cross-group assignments also fail explicitly when their target separation
contradicts measured concurrency. Missing or ambiguous targets remain failures;
they do not inherit another cap's timestamp or input evidence.

`beat-timing.json` retains measured pairs under `native_chords`, and accepted
fits retain `native_chord_constraints` plus `unconstrained_row_domains`.
Unresolved domains and contradictory assignments remain report warnings. This
does not suppress motion/visibility warnings or identify a chart gimmick.

## Independent spacing constraints

A broad time interval can also cover several nonconcurrent rows. Use uniquely
placed heads as independent anchors in each registered coordinate block,
including nearby measures at the same tempo. A model needs at least five other heads, two
lanes, three distinct target times and a target span of at least 300 ms.
Every reference must satisfy the existing one-pixel model residual limit;
no disagreeing reference is discarded. The tested head needs qualified native
measurement support and cannot train its own model.

Apply a model only when the entire candidate row domain lies between its
independent anchors. Intersect the existing row domain with the measured
coordinate interval, using the reference model's actual maximum residual plus
the existing 1.5-pixel native support limit. Models can remove candidate rows,
never add one or enlarge a time interval. Every qualified block constrains the
result; conflicting evidence cannot be bypassed by selecting a favorable block.
Singleton row domains receive the same check: one possible row is not proof
that its time agrees with the independently observed native position.
At each candidate song phase, freeze unique rows from the initial independent
group fits before comparing neighboring groups. Newly resolved heads are not
reused as training anchors within this operation. A reference must retain its
original target in the final fit; changed or failed references explicitly fail
dependent groups. Measure boundaries do not discard native support, and tempo
changes do not transfer reference timings between groups. The local and combined
reference models constrain the domain separately. An incompatible combined
model cannot erase a valid local constraint; two qualified but contradictory
models fail rather than selecting the preferred one.

Also fit the frozen neighboring heads alone over the tested beat group's time
span plus the ordinary reference radius on either side. This independently
bracketed model does not use the group's own row assignments as training data.
It can refute a locally consistent but shifted group. It keeps the same source
coordinate block, tempo, reference-count, residual and native-error requirements.

One surviving row resolves the ambiguity. Multiple survivors remain explicitly
ambiguous; no survivor refutes that head's assignment. Retain other confirmed
heads as a partial fit while testing a finer natural Split. A fully supported
finer fit can restore the refuted head; finer ambiguity cannot erase more
confirmed rows from the coarser partial fit. All ordinary time and geometry
limits remain. Final spacing and chord checks still apply. No input observations,
result quotas or existing chart notes supply these row constraints.

`native_coordinate_constraints` retains the original and allowed row domains,
source note identity, coordinate block, model error and each independent
reference's native support and source PTS range. Failed ambiguous fits also keep
their remaining row domains and any qualified coordinate constraints.

When an independently modeled pair has a conflicting gap, compare each head's
actual native offset with the model separately. Keep a head when every qualified
model places it within the existing native-plus-reference error bound and only
its neighbor contradicts that bound. If models refute both heads, disagree on
which head is wrong, or cannot attribute a relative gap error, both remain
unresolved. Preserve pair evidence and per-head residuals in the warning.

## Targets without a successful crossing clock

A continuous trajectory can lose its shared crossing clock when peers disappear
or rendered spacing changes. A failed clock does not erase qualified native
positions earlier in the approach. Independently timed, already restored beat
rows can bracket that head in the same registered coordinate block.

Freeze accepted references before recovery. The rejected estimate selects only
a bounded reference neighborhood; it supplies neither the accepted time nor an
error interval. Fit offset against reference target time using the ordinary
five-head, two-lane, three-target, 300-ms and one-pixel requirements. The tested
head retains its native-support gate. Its entire inferred interval must lie
inside the reference target span and a single tempo section. Every qualifying
block must agree. Recovered heads cannot become references in this pass.

Require one natural beat row in the measured interval, at the already selected
common song phase, with the subdivision also explaining every reference row.
No surviving row or several survivors remains failure. Preserve the spatial
interval and alignment uncertainty in the published target range. This proves
chart timing from relative note placement; it does not measure or fabricate a
source motion clock, receptor crossing frame or input time.

Final spacing and concurrency validation still apply, including to heads
without source clocks. A reference that fails final validation invalidates its
dependent recovery. Only a successful final recovery retires that head's
`shared_timing_reconstruction_failed` warning; unrelated visibility, motion,
processing and input warnings remain. The original failed attempt stays on the
note under `previous_motion_attempt`. `native_coordinate_recovery` retains all
qualified block models, original PTS ranges, selected row and failed attempts.

A clock may succeed yet produce a beat assignment contradicted by native
positions. That rejected assignment can use the same independent recovery, with
stricter reference selection: exclude the entire tested group and every
reference whose row required native refinement or recovery. Each remaining row
must be unique in its original clock interval and stay inside it throughout the
selected common phase range. Use a fixed window covering the tested group's
clock intervals plus the ordinary reference radius; references still need the
same native block and tempo section, and must bracket the whole inferred range.

The rejected clock interval only selects the neighborhood. It cannot veto a
separately proven native target or be enlarged to accommodate one. Preserve it
as `rejected_clock_target_range` and retain `rejected_beat_assignment`. Only
final validated recovery retires the corresponding beat-failure warning;
unrelated motion, input and visibility warnings remain. An ambiguous beat
assignment can use the same external references, but must intersect the native
prediction with its original clock interval before selecting a row. An empty
intersection or several remaining rows fails explicitly. Other beat failures
do not qualify for this path.

Validate known rows for spacing and concurrency before freezing recovery
references. A row which already failed either check cannot train recovery.
After recovery, apply the same checks to pairs involving newly assigned rows;
unchanged pairs retain their first-stage validation and warnings. Newly
discovered contradictions still invalidate
their dependent recoveries; there is no repeated pruning to fit a preferred
answer. Both validation stages retain their diagnostics.

A recovered head's frozen reference set can also validate its gap to a neighbor
in the same native block. Remove both tested heads from that set and refit with
all remaining validated references under the same count, span, error and
bracketing gates. This preserves independent evidence when a narrower local
window has too few references. Every other qualifying pair model still applies;
a favorable recovery model cannot bypass a contradictory one.

## Partial groups at a fixed common phase

A compatible subdivision can give one row to some heads and several rows to
another. Keep the unique assignments and mark the unresolved head as failed.
A group records `status: partial`, null rows/targets for unresolved heads and
its remaining domains. It cannot silently select one of those rows or increase
Split merely to hide ambiguity. A group with no unique assignments remains
failed. Contradictory domains and unsupported subdivisions still fail.

The common-phase search counts only unique assignments and validates them with
the ordinary spacing and chord checks. Winning phases must agree on those
assignments and supported identities; the chosen midpoint is checked again.
Each partial fit uses one fixed common phase. Unknown phase cannot independently
move a head or bypass the common-phase search.

Per-note reconstruction records its own success/failure and references the
shared beat-group record by `group_index`. A failed head keeps its original
video range, a null accepted target and an explicit reconstruction warning.
The analysis remains failed while any such warning survives. Independent unique
neighbors can still supply geometry and input associations, subject to all
ordinary checks; unresolved heads cannot participate in those accepted matches.
