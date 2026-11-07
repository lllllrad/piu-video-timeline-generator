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
required role features. The original cap comparison and raw source PTS remain
available to coordinate and track consumers.

Connector pixels already positively measured as part of this cap are excluded
from a second, potentially incompatible animation comparison. At least half of
the original connector footprint must remain independent. Every remaining
spatial cell must pass; another measured cap covering it makes it unavailable.
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
