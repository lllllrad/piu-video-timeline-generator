# Independent role evidence around image-matched caps

A tap image's background changes with the song animation. Comparing its upper
and lower margins to reference RGB can leave a clearly matched cap without a
role. The optional `phoenix_chromatic_gap` model instead combines the positive
cap image with independently retained spatial masks around that cap. It does
not detect heads or infer their times, and a failed hold match does not prove
a tap.

A failed endpoint-connector reference can also use independently matched body
images from the same original frame. `skins/connections.py` unions only their
positively compared `body` pixels, including retained alternatives. It requires
every declared connector pixel of a positive cap comparison to be covered.
Nearby tiles, bounding rectangles, cap-internal body subfeatures and even a
single unmeasured connector pixel cannot establish a connection. The result
retains the actual body-comparison indices, connector support and original PTS.
Moving-cap observations establish object identity using the same distinct-frame
and travel requirements as tap evidence. Once that identity is established,
one fully measured connector can supply a positive role observation.
No judgment or input channel supplies
these hold roles; downstream endpoint ownership and timing must still succeed.

A versioned bank can declare this model in `roles.json` beside `bank.json` in
the separate skin repository:

```json
{
  "schema": 1,
  "bank_contract": {"skin": "the-bank-skin-identity", "sha256": "EXACT_BANK_HASH"},
  "clearance": {
    "model": "phoenix_chromatic_gap",
    "skin": "the-bank-skin-identity"
  }
}
```

`bank_contract` must contain the complete contract returned by the native bank
loader, not only the abbreviated fields shown above. Automatic and manual skin
selection use the same declaration. A source profile's explicit `role_clearance`
overrides it; `null` disables the model for that source profile. A changed bank
contract fails rather than inheriting another bank's geometric assumptions.
`just skins validate` also validates these declarations.

The bank must provide all five kinds of hold body. At native feature resolution, every
supported row of every positive `body` region must retain its declared lane color in
the central 0.2-spacing-wide body core of the relaxed-color plane. Clearance
probes cover that core plus the allowed 0.1-spacing cap-anchor disagreement on
each side. Interpolation context outside the declared body region supplies no
body measurements. Reference gap boxes locate the vertical bands; horizontal
measurement expands to cover the complete possible body core in actual retained
game pixels, even when the reference background box is narrower. Lane colors must follow blue/red/yellow/red/blue.
White-only, dark, differently colored or incompletely sampled bodies need a
different model. Unsupported configuration produces an explicit report warning.

For each existing image observation, the model requires:

- A positively matched tap-cap reference with source-bound native registration.
  Its upper and lower clearance boxes must both be declared outside the cap.
- A positive cap match is usable inside a documented HUD footprint. Both
  clearance boxes must remain outside potential HUD coverage and lie entirely
  within actual acquired pixels; padding is not background.
- No relaxed lane-color pixel in either clearance box, and less than 5% white
  coverage. A saturated effect, colored connection or known overlay leaves the
  role unresolved. Black acquired pixels can establish a gap for this explicitly
  validated bright-body model.
- A moving object established by positive cap matches at four distinct original
  PTS and cap positions, with half a lane spacing of travel. At least one frame
  must satisfy both clearance tests. The movement observations and role
  observations have separate purposes; an obscured margin does not erase a cap
  match or a role observed in another frame of the same acquired trajectory.
  This combines role evidence without interpolating motion or blank pixels.
  Elapsed duration does not qualify a type: the required spatial travel and
  distinct positions prevent repeated render frames from adding support at any FPS.
  Repeated capture frames and stationary receptor artwork cannot supply this
  moving-cap proof.

Image margins are mapped to masks using actual horizontal and vertical scales,
rounding outward to retain every potentially relevant pixel. The source image
anchor and its native registration remain unchanged. No nearest beat row,
counter value, judgment word, grade total or input effect supplies a tap role.

`skin-role-evidence.json` stores the profile, model and acquisition contracts,
original PTS, cap-reference identities and measured clearance boxes. It is a
derived interpretation of `frames.jsonl` and `native-features/`; both native
artifacts remain immutable. Changing this model reuses saved masks without RGB
decoding or OCR. Missing or incompatible acquisition fails explicitly.

The common role reader merges the additional tap observations before hold
reconstruction and channel reporting. It retains all original observations. A
positive hold image plus qualified tap clearance becomes a role conflict and
remains warned; this model does not suppress that conflict. Already observed
tap roles need no duplicated per-frame evidence. The new role alone supplies
neither a chart target nor an input timestamp.


## Lost body coverage and measured displacement

Frame-to-frame body coverage uses independently measured cap displacement. When
the source coordinate stage supplies a bounded displacement, the motion record
retains `displacement_range_pixels` with the exact original PTS pair. Invalid
bounds or a mismatched PTS pair cannot fall back to an unbounded point estimate.

For a previously compared body interval `[a,b]` and displacement `[lo,hi]`, only
`[a-lo,b-hi]` is guaranteed to remain visible under every supported shift. The
loss check compares that common region against current positive image spans and
documented occluders. It never enlarges current image support or turns possible
pixels into body evidence. Missing interior or endpoint regions still produce
explicit warnings with their displacement bounds.
