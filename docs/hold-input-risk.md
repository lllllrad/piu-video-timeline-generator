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
  hold's measured interval and cap neighborhood.
- All known holds have uncensored image endpoints, repeated body evidence and
  measured endpoint motion. The word precedes every relevant held-state interval.
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
