# Hold visibility and input risk

A moving hold may be seen well before it reaches the receptors. Missing image
coverage during that approach is a visibility warning, not evidence that its
ticks can occur throughout the approach.

`play/holds/input_risk.py` owns the shared risk check. Known hold start/end
ranges, native receptor-body observations and unaccounted connected-body
candidates remain separate inputs. Image-tile summary warnings do not establish
continuous held states; their actual receptor risk requires a complete current
image profile as described in [play analysis](play-analysis.md).

A known hold's connection-visibility warning can use that hold's existing time
bounds only when the warning identifies exactly the same head, tail and hold,
both endpoints are uncensored, and repeated positive image regions establish
the body. The native profile must also be current and complete. Missing caps,
censored endpoints, unrelated fragments or conflicting identities keep their
conservative unresolved intervals. Visibility warnings remain in the report.

No warning interval supplies a new chart target, press time or held state.

## Deferred words before measured holds

A native PERFECT/GREAT/GOOD/BAD refresh can be excluded by the initial 100 ms
guard around a future body observation. After image roles and complete hold
geometry are available, a second pass can reconsider that refresh only when:

- The target has a confirmed tap role. Hold components, MISS candidates and
  already assigned notes remain unavailable.
- The image profile provides current receptor-body observations. Every nearby
  risk flag responsible for the initial exclusion fits within a known future
  hold's measured interval and cap neighborhood, or has exact native image
  ownership establishing that the hold is still approaching.
- All known holds have uncensored image endpoints, repeated body evidence and
  measured endpoint motion. The word precedes every relevant held-state interval.
  A failed musical beat assignment does not invalidate native geometry: an
  endpoint may use its restored native crossing interval when that exact interval
  is recorded as the hold's owned endpoint. Failed native reconstruction,
  unrelated exclusions and mismatched endpoint intervals cannot supply a guard.
  A cap neighborhood uses the larger of one lane spacing and the reference
  bank's maximum vertical cap extent, divided by the slower measured endpoint
  velocity, with a minimum of two capture frames. A changed or missing bank
  cannot supply this proof. Unaccounted connected
  bodies and native risk overlapping the word still block recovery.
- Strict row alignment remains unique while all valid unowned word refreshes
  and unknown note rows remain competitors. Existing refresh ownership and
  predecessor/successor anchors remain fixed. The original 45 ms association
  tolerance applies.

The supplied display correction is used when comparing word time with visual
hold risk. This comparison never shifts the retained native word bracket.
Recovered matches cite the original judgment event and retain its grade and
full range; they do not invent receptor onsets or assign an uncertain counter
refresh. Connection-visibility and processing warnings remain independent.

## Native proximity ownership

The native detector's proximity flag includes long bodies near, but still below,
the receptor. `body-risk-evidence.json` derives all causes of every positive flag
from saved `frames.jsonl`; the original flags and acquisition thresholds remain
unchanged. The derived artifact verifies every native flag, frame count, original
PTS ordering and the exact grouping of unsupported intervals. Missing or
inconsistent observations produce an explicit warning.

Each cause can belong to a hold only through a same-frame, same-lane temporal
image component containing its entire vertical extent. Multiple possible owners
remain unresolved. An approaching state additionally requires a registered cap
coordinate, its uncertainty and conservative full cap extent entirely below the
receptor, a body below the receptor, and positive registered upward displacement.
An unregistered cap or a stationary/reversed observation cannot establish this
state.

A popup can precede such an interval only when every cause has one complete
future hold as owner, each owner's first frame proves approach, and the word is
outside that hold's measured start and cap neighborhood. Later frames may reach
the receptor but must keep their exact ownership. Any unowned cause, including
another lane or another cause in the same frame, retains the veto. Only that
fully accounted native interval is removed from the proximity veto; known held
states and other unresolved bodies still block association. The source, skin,
hold components, coordinate registration and native intervals must match the
artifact contract. Timing evidence never supplies this geometric ownership.

The report shows proximity causes, owners and approach states inside the moving
note channel. This is a derived interpretation of native images, not an
additional independent input signal.

Lane-supported row recovery uses the same strict target-time window for both
nominal display correction and observed local offset before comparing refresh
alternatives. A distant candidate from the wider review window cannot veto a
refresh it could never replace. Multiple temporally plausible refreshes remain
alternatives even if only one has independently confirmed lane evidence.

## Sustained-response bounds with unresolved beat rows

The response window uses the reconstructed hold's endpoint ranges. A missing
musical target on its source tail is not playback zero and cannot move the
window back to an earlier note. Following observed caps still bound the trailing
response guard, including caps with failed beat placement but valid native timing.
Unknown native timing cannot supply such a bound. Recognition still requires
actual retained receptor support; this calculation cannot turn a window into
an observed press, release or held state by itself.
