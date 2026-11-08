# Shared cap appearance and hold context

A cap appearance and a hold connector are independent positive measurements.
A known glyph must not become unrecognized solely because an endpoint reference
was captured at another animation phase. Reference banks explicitly opt into
sharing; matching skin names, colors or nearby positions never enable it.

A bank can declare `shared_cap_families`:

```json
{
  "shared_cap_families": [{
    "id": "blue-common-cap",
    "appearance_templates": ["blue-cap-pose-a", "blue-cap-pose-b"],
    "role_templates": ["blue-start-context"],
    "body_templates": ["blue-body"]
  }]
}
```

Every member belongs to one lane kind. Appearance entries are cap references;
role entries are hold starts or ends. Optional body entries are positive body
references. This declaration asserts shared glyph geometry and native-center
conventions, not a tap classification. A neutral cap reference can use `tap`
without clearance regions: it establishes an appearance while its role remains
unknown. An end with distinct identifying artwork requires its own appearance
and/or independent `cap_features`; sharing never skips those required features.

The detector first retains ordinary cap and body comparisons. For a declared
family, it aligns role context to the measured cap's native center. Each context
keeps its own reference, sampling phase, canvas bounds and errors. Its anchor
never replaces the cap's coordinate or supplies chart timing. A classification
requires a positive connector on the declared side, and all independently
required role features. The original cap comparison, acquisition method and raw source PTS remain
available to coordinate and track consumers, including when a grouped alternative
provides the successful appearance. Replay validates each native frame before
writing it; invalid detector evidence cannot consume the rest of the recording
or replace the published native trace.

Connector pixels already positively measured as part of this cap are excluded
from a second, potentially incompatible animation comparison. At least half of
the original connector footprint must remain independent. Every remaining
spatial cell must pass. A positively measured foreground cap may hide part of a
connector, provided at least half of the independent support in every nonempty
spatial cell remains visible. Every visible cell keeps its original RGB limit.
A fully hidden cell remains unavailable; negative tap-clearance checks and
required terminal features still require their complete support.
A hidden connector never becomes positive from a presumed chart or scroll rate.

If a connector RGB reference does not match, explicitly listed body references
can establish the connector only when their positive two-dimensional support
covers **every remaining connector pixel**. Remote body tiles, cap subfeatures
and unsupported gaps cannot do this. The failed direct reference error and all
used body comparisons are retained. This uses actual body-pattern measurements,
not lane brightness or a guessed connection.

`shared_role` stores the family, original cap role, measured cap rows and the
independent context. `context.body_coverage`, when present, names the coverage
method, failed direct RGB error, pixel count and body observations. Classification
does not merge endpoints or create another press: a hold remains a sustained
interval. Conflicting qualified roles remain conflicts.

Hold geometry consumes only the measured cap and connector rows. Tap clearance
bands from an appearance reference are negative evidence and never become
positive body support. Receptor-risk, image connectivity, role joins and native
coordinate projection retain the independent evidence. A family change
invalidates cap classification while body acquisition remains separately reusable.
Changing a body reference used by a family also invalidates dependent cap
classifications; their stored coverage proof cannot refer to superseded pixels.

Synthetic integration varies reference appearance counts independently by role.
It checks exact cap counts, per-frame roles, native centers/PTS, separate hold
connections and warnings at multiple scales, including cut-corner artwork.
Negative tests cover absent connections, remote body evidence, missing references,
cross-lane sharing and required tail features. Source-specific images and
recognition fixtures belong in the separate skin/chart data repository.

Partial connector evidence retains the visible two-dimensional runs and exposes
only those rows to body connectivity and receptor consumers. Foreground removal
never grants body support to a hidden pixel. The same per-cell rule applies to
ordinary overlapping endpoint references and declared shared-cap contexts.

Short holds can place the start artwork over the tail reference's upper body.
A complete long-hold tail reference can then fail even while its terminal border
is visible. Partial connector comparison alone does not solve missing cap
appearances, hidden identifying tail features, or an entirely covered connector
cell. Nearby frames must provide the missing positive evidence; a fixed overlap
that persists across frames needs a separately validated short-hold pattern.
Neither an expected hold duration nor a nearby terminal-like line establishes it.

## Body-only temporal continuity

A long hold's start can leave the visible field before its tail enters it.
Uniform body pixels do not supply a vertical displacement measurement. A missing
cap-motion sample therefore cannot, by itself, refute the continuously observed
body or turn its two recognized endpoints into separate notes.

When measured displacement is unavailable, consecutive native frames can link
positive body intervals in the same lane if their actual overlap includes at
least half a lane spacing. Both playback and original PTS gaps must be at most
50 ms. Only compared body/connector rows count; a cap silhouette, presumed speed,
HUD rectangle or interpolated interval cannot supply this edge. The proof records
its observed overlap and source timestamps as `body_continuity_links`, without
creating a `motion_link` or any timing clock. Missing images and capture gaps
break this support. Competing endpoint identities and intervening taps retain
their existing conflict rules. Missing motion/coverage remains separately
reviewable even when the body identity can be connected.

## Distinct terminal artwork

An endpoint reference may declare `cap_role_identification: "distinct_full_cap"`
when its complete cap artwork identifies its role independently of a body neck.
This is an explicit skin fact, not an inference from color, a template filename
or an expected chart. It is available only to endpoint references; undeclared
banks continue to require the full cap-and-connection pattern.

Every required cap region and identifying feature keeps its original RGB limit.
A recovered partial cap cannot use this declaration. If the complete distinct
cap matches but its connector does not, the observation retains the known role
with `classification_status: "cap_role_pattern"`. Its failed connector error is
preserved, and `role_evidence` names the separate identification rule. Only the
actually compared cap footprint supplies positive support; no failed connector
or missing body row becomes positive evidence.

A bank may instead declare `cap_role_identification: "distinct_cap_features"`
with a nonempty `cap_features` list. This asserts that those specific image
features distinguish the endpoint from taps, other endpoints and bare stems.
Reference controls must establish that distinction; an arbitrary colored patch
is insufficient. The cap comparison and every named feature retain their RGB
limits. Every supported pixel of every discriminating feature must be actually
visible and compared. A hidden or damaged feature, missing visibility footprint
or unexplained obstruction cannot qualify.

This rule can identify a recovered partial cap or one with an unverified mixed
boundary while its discriminating artwork remains complete. It preserves the
actual `visible_cap_runs` and existing observed connector runs, rather than
filling the cap or body silhouette. `role_evidence` names the feature rule and
its discriminators. This establishes a role only: it neither connects a head
to a tail nor supplies endpoint timing or missing body pixels.

This boundary is useful for short holds whose start drawing occupies part of a
long-neck reference window. A known tail remains a tail even if its body link is
unresolved. It cannot become an additional tap; unpaired tails keep explicit
geometry warnings and remain excluded from independent chart-note projection.
A full competing tap/start pattern remains a role conflict. Source-bound native
centers and source PTS are unchanged by a role declaration.
