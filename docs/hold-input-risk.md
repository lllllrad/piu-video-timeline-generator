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
