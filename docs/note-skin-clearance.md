# Native clearance around image-matched caps

A tap image's background changes with the song animation. Comparing its upper
and lower margins to reference RGB can leave a clearly matched cap without a
role. The optional `phoenix_chromatic_gap` model instead combines the positive
cap image with independently retained spatial masks around that cap. It does
not detect heads or infer their times, and a failed hold match does not prove
a tap.

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
- At least four distinct original PTS across 65 ms, no adjacent observation gap
  above 50 ms, four distinct cap positions and half a lane spacing of travel.
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
