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

A broad time interval can also cover several nonconcurrent rows. Within the
same beat group, use uniquely placed heads as independent anchors in each
registered coordinate block. A model needs at least five other heads, two
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
Newly resolved heads are not reused as training anchors within this operation.

One surviving row resolves the ambiguity. Multiple survivors remain explicitly
ambiguous; no survivor refutes the subdivision. A finer natural Split can be
tested after a refuted coarse Split, with all ordinary time and geometry limits
preserved. Final spacing and chord checks still apply. No input observations,
result quotas or existing chart notes supply these row constraints.

`native_coordinate_constraints` retains the original and allowed row domains,
source note identity, coordinate block, model error and each independent
reference's native support and source PTS range. Failed ambiguous fits also keep
their remaining row domains and any qualified coordinate constraints.
