# Basic recognition cases and expected results

This is a behavioral specification for synthetic scenes, independent of the
current detector and its thresholds. It defines the ordinary support target;
it does not claim that the implementation or existing tests meet that target.
The [visual model](gameplay-visual-model.md) defines the game interpretation.
[Recognition validation](recognition-validation.md) describes test boundaries
and promotion order.

## Scene truth and result vocabulary

A scene defines these inputs separately, before rendering or analysis:

- Chart objects: lane, tap alignment time, or hold alignment start/end. A hold
  has one held interval and two visual boundaries, with no implied extra tap.
- Screen: crop, receptor centers, lane centers, cap/body shapes and reference
  anchors. Dimensions and positions may be fractional before rasterization.
- Motion: displacement as a function of game-render time. Chart identity and
  motion are independent of input success.
- Capture: recording times, original source PTS and the game-render time sampled
  at each captured frame. Duplicate renders and missing captures are distinct.
- Display events: judgment label/refresh, combo value/refresh, lane-local light
  and visible processing of each object. These can disagree or be absent.
- Foreground/background: named HUD footprints, actual opaque pixels, flashes,
  clipping and artwork. A potential foreground rectangle is not opaque proof.
- Declared support: layout and skin, and any concrete chart mechanic handler.

The oracle lists chart objects, visible image roles, observable event brackets,
permitted associations and required unresolved states. It must not copy the
recognizer's output or fit its parameters to that output. Reference artwork and
rendered test frames may share a declared skin, but whole reference frames must
not simply be replayed as the only positive examples. Vary placement, background,
scale, capture phase and neighboring objects.

"Preserve" means retain identity and source observations; it does not require a
cap measurement in a frame where relevant pixels are hidden. "Warn" means an
explicit unresolved diagnostic linked to its actual observations and interval.
The wording or internal warning code is not the oracle. No evidence is different
from negative evidence; neither supplies a successful input.

For a fully observable ordinary case, require the exact object count, lanes and
types with no missing/extra object and no unexplained loss/type/geometry warning.
Target intervals must contain scene alignment truth under the declared capture
and registration error model. Missing calibration remains explicit; synthetic
anchor truth cannot certify an actual game's engine timing. An input estimate
must be justified by display evidence and its declared delay model, not by the
chart's alignment time. UCS must preserve supported objects and simultaneous
rows; an unresolved object must have an explicit rejected placement.

## Chart objects and image roles

Each positive case has intact moving observations before receptor overlap. Hold
cases include positive connection evidence; two-tap controls include a visible
background gap. Sample multiple distinct positions, rather than repeated copies
of a stationary sprite.

| ID | Scene | Expected result |
| --- | --- | --- |
| O01 | Empty moving field, active background without moving note-like artwork | Zero chart objects; no inferred input or chart row |
| O02 | One tap in each lane, separately | One tap per scene, in the specified lane; preserve its trajectory and target |
| O03 | Two/three/full-panel chord with common target | Exact lane set at one row; no missing chord member or sequentialized row |
| O04 | Close cross-lane stagger with distinct observable alignment times | Separate targets; never force a chord; warn if capture cannot distinguish the rows |
| O05 | Repeated same-lane taps, including a dense sequence | Exact number and order; do not join their caps or reuse one event for all taps |
| O06 | One long hold with both caps and connection visible | One hold with the specified endpoints; no tap at either cap |
| O07 | One short hold whose connector is distinguishable from a gap | One short hold; duration alone cannot turn it into two taps |
| O08 | Two taps with the same cap separation as O07, but a clear gap | Two taps; no hold formed by morphology or template padding |
| O09 | Leading cap has passed, body remains at the receptor | Continue the same hold; remaining body is neither a new cap nor a new press |
| O10 | Trailing cap looks like a tap with connection above it | End the same hold; no additional tap or required input onset |
| O11 | Two adjacent holds separated by a distinguishable gap | Two source holds with separate identities; no spanning image connection |
| O12 | Real tap immediately before/after a same-lane hold | Preserve both objects; endpoint uncertainty cannot absorb the independent tap |
| O13 | Independent tap and hold in different lanes overlap in time | Preserve both objects; hold ticks cannot consume the tap's lane evidence |
| O14 | Hold begins before or ends after available recording | Preserve observed hold and censor the unseen endpoint; no invented finite endpoint or silent UCS placement |
| O15 | Positive cap but its connection/clearance is unobservable | Preserve cap observations; unresolved type/geometry, rather than assumed tap or hold |
| O16 | Same object has incompatible complete tap and hold-role observations | Preserve both observations and warn about the conflict; majority vote cannot silently clear it |
| O17 | Body images without provable endpoint ownership | Preserve them and warn; no headless complete hold or invented endpoint |
| O18 | Independently observed cap inside a proposed spanning connection | Preserve the cap and reject/warn about incompatible ownership; do not erase it to finish a hold |

UCS simplification is a later consumer: multiple proven held intervals may become
one equivalent sustained requirement only when the intervening gap does not need
a release/repress. Source object identities and geometry stay separate. Actual
input observations may support that simplification, never replace visible chart
objects with the player's actions.

## Visibility and identity across frames

| ID | Scene mutation | Expected result |
| --- | --- | --- |
| V01 | Cap disappears under intersecting judgment/combo foreground and returns uniquely | One object; retain the explained occlusion and reappearance, with no clear-field loss warning |
| V02 | Same foreground lies in another lane | It cannot explain this object's loss; warn for the unexplained missing observations |
| V03 | HUD rectangle overlaps but pixels remain visible and positively matched | Retain positive image evidence with overlap provenance; do not discard it solely for rectangle overlap |
| V04 | Missing detection in an otherwise clear source frame | Warn even if adjacent frames establish timing/type/hold ownership |
| V05 | Missing body/cap support later explained by an independent positive image channel | Retain original missing evidence and exact corroboration; explain only its measured region |
| V06 | Cap is obscured by white effects or unavailable visibility pixels | Unknown measurement, with no positive shape, absence or input claim; unexplained continuity stays diagnostic |
| V07 | Cap leaves foreground but never returns to the expected clear field | Warn after the predicted exit; foreground cannot excuse the whole remaining trajectory |
| V08 | Two plausible successors after an occlusion | Preserve ambiguity; do not force one identity or silently drop the other |
| V09 | Top/bottom/image edge clips cap or connection | Keep partial measurements separate; do not treat clipped centers as intact anchors or edges as hold endpoints |
| V10 | Partial connection support covers only some missing rows | Explain only those rows; retain the remaining body-gap warning |

## Capture, geometry and motion

| ID | Scene mutation | Expected result |
| --- | --- | --- |
| T01 | Constant speed, multiple capture phases at 30/60/120 fps | Same objects and row order; truth inside timing intervals without integer-frame target snapping |
| T02 | Short sequences of captures repeat one render, then movement resumes | Preserve source frames/PTS; repeated position cannot add independent movement support or force a stop |
| T03 | Known dropped captures or irregular gaps near alignment | Timing/event brackets include the resulting uncertainty; no pretend intervening measurements |
| T04 | Long capture freeze or recording cut across processing | Explicit unresolved/freeze/boundary evidence; no fabricated exact event or hidden failure |
| T05 | Resize, crop translation and nonidentical horizontal/vertical scale | Same object identities, lanes and physical time; use actual axis transforms and retain scaled uncertainty |
| T06 | Fractional anchors with rasterization noise | Truth inside the error bound; no manufactured chord/stagger from rounding alone |
| T07 | Musical rows not unique under the observed timing bounds | Preserve native objects and explicit beat-placement failure; no arbitrary selected row or dropped object |
| T08 | Natural fine subdivision or triplet with otherwise supported timing | Preserve row relationships using appropriate UCS subdivisions; split choice does not set measurement error |
| T09 | Speed change, ramp, stop or reversal without configured handling | Preserve observations and explicit unsupported/changed-motion diagnostics; no constant-speed extrapolation through the change |
| T10 | Same motion change with a concrete scoped handler | Apply measured/configured behavior only in scope; conflicting motion still warns |

## Four evidence channels and associations

The channels are popup judgment/combo refreshes, receptor effects, moving chart
objects, and their processing/disappearance. Keep their native observations and
count units independently. A refresh can account for a row; it does not become
one independently measured press per member. Retaining evidence and establishing
a unique association are separate requirements.

| ID | Available evidence | Expected result |
| --- | --- | --- |
| E01 | No popup, receptor effect or processing event | Chart objects remain; warn about missing timing evidence; no successful input inferred from chart presence |
| E02 | Unique judgment refresh, combo absent (including first notes) | Preserve the refresh bracket and grade; associate where row ownership is independently unique |
| E03 | Unique combo update, judgment label unreadable | Preserve count/bracket evidence; do not fabricate a grade |
| E04 | Lane-local receptor change with no popup | Preserve local event/bracket; no invented grade or success solely from light |
| E05 | Verified cap disappears near receptor, no other input channel | Preserve processing bracket; disappearance alone does not prove successful judgment or physical press |
| E06 | All available channels agree | One compatible association using original brackets; no duplicated event or artificial intersection of unrelated clocks |
| E07 | Channels disagree on lane, time or grade | Preserve the disagreement and warn; do not choose whichever channel fills a quota |
| E08 | Popup persists through several chart rows without refresh | One original display event, not new judgment evidence per row |
| E09 | Chord refresh with light on only some lanes | Retain aggregate row evidence and partial lane evidence; no invented local effect for the remaining lanes |
| E10 | Sustained hold light and repeated ticks with no new press | Held recognition intervals, not repeated tap inputs; cap disappearance remains hold-component evidence |
| E11 | Common flash across receptors | No independent per-lane input transitions inferred solely from the flash |
| E12 | MISS refresh | Failure/grade evidence without physical input time or required screen-to-input connection |
| E13 | Two rows can own one refresh under available uncertainty | Preserve alternatives and explicit ambiguity; no silent duplicate ownership |
| E14 | Counter jumps across unseen intermediate updates | Retain aggregate uncertainty; do not invent intermediate display frames |
| E15 | Declared simultaneous counter increment of a concrete amount | Apply that counting semantic only in its region; retain source bracket and require compatible row ownership |

Compatible stage-result totals must agree with analyzed judgment units. A conflict
is a diagnostic; totals never supply missing events, grades or chart objects.

## Required combinations and acceptance order

First establish O01-O18 with ordinary upward motion, declared layouts and
distinguishable static skin roles. Include Single-left, Single-right and Double,
and blue/red/center artwork with different cap and tail silhouettes. A supported
skin needs this functional coverage; an arbitrary cap image is not a validated
skin. Random per-note skins and downward modes remain explicitly unsupported.

Next combine object cases with visibility and capture variations, then independent
channel availability. Required interaction groups are short hold versus two taps
under resizing; hold caps/body across foreground and flashes; adjacent holds and
real neighboring taps across capture gaps; chords/staggers with partial or
conflicting evidence; and source-time uncertainty through UCS placement. Also
check damaged/stale channel artifacts and changed source identity: fail explicitly
before consuming incompatible evidence, preserving previous valid output.

For each case, record its scene definition, expected result, generator support and
checks at the pixel, stored-observation and connected-stage boundaries. Do not mark
it verified from an unrelated unit test or a missing assertion. Implementing this
matrix and discovering existing failures precede further recording-driven rule
tuning. Recordings then test generalization and introduce new generic cases.

## Mechanics after the ordinary baseline

For gameplay-affecting mechanics, use recordings to identify the intended rule,
its song-relative interval and concrete parameters. Then reproduce that rule in
the synthetic scene generator before promoting its processor. Human-authored
patterns commonly have structure; a list of unexplained exceptional frames is
not an adequate mechanic model.

Examples are a measured speed multiplier or ramp, stop duration, visibility
period/phase/duty cycle, or a simultaneous judgment increment of a specified
amount. Retain the source observations and uncertainty establishing those
parameters. Motion, chart rows and input/display events remain independent scene
inputs. Test entry/exit boundaries, neighboring ordinary objects, interacting
holds/chords, capture gaps and a deliberately contradictory measurement.

Chart metadata selects the region and parameters for a concrete handler shared
by ordinary consumers. A supported effect must produce appropriate chart/timing,
visibility and input semantics; its name alone cannot suppress diagnostics.
Unidentified or contradictory behavior remains explicit. Decorative intervals
without gameplay requirements use an explicit non-playable role and preserve
their raw observations, rather than inventing notes or inputs.
