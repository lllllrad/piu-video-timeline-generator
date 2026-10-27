# Native clearance around image-matched caps

A tap image's background changes with the song animation. Comparing its upper
and lower margins to reference RGB can leave a clearly matched cap without a
role. The optional `phoenix_chromatic_gap` model instead combines the positive
cap image with independently retained spatial masks around that cap. It does
not detect heads or infer their times, and a failed hold match does not prove
a tap.

Enable the model explicitly in a selected source profile:

```json
{
  "schema": 1,
  "profiles": [{
    "segments": [1],
    "bank": "relative/path/to/bank.json",
    "role_clearance": {
      "model": "phoenix_chromatic_gap",
      "skin": "the-bank-skin-identity"
    }
  }]
}
```

This configuration belongs in the ignored source's `note-skins.json`. The bank
must provide all five kinds of hold body. At native feature resolution, every
supported row of every body reference must retain its declared lane color in
the central 0.2-spacing-wide body core of the relaxed-color plane. Clearance
boxes cover that core plus the allowed 0.1-spacing cap-anchor disagreement on
each side. Lane colors must follow blue/red/yellow/red/blue.
White-only, dark, differently colored or incompletely sampled bodies need a
different model. Unsupported configuration produces an explicit report warning.

For each existing image observation, the model requires:

- A positively matched tap-cap reference with source-bound native registration.
  Its upper and lower clearance boxes must both be declared outside the cap.
- The complete cap and both boxes outside documented HUD footprints. Boxes
  must lie entirely within actual acquired pixels; padding is not background.
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
