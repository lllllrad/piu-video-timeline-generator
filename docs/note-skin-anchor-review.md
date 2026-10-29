# Reviewing note-skin reference anchors

## Same-cap comparisons

Before activating a candidate bank, compare references that matched the same
acquired cap:

```sh
mise exec -- python -m piu_timeline.play.skins compare-anchors \
  .local/reports/image-review/observations.json \
  --bank .local/cache/note-skins/example/bank.json \
  --output .local/reports/image-review/anchor-pairs.json
```

This saved-data review checks bank identity and native timestamps without decoding
video. It chooses each reference's strongest qualified cap comparison per acquired
cap, including every required cap feature. It retains both witness coordinates,
original PTS, observation index and the signed second-minus-first difference.
Repeated relative offsets can reveal an inconsistent reference anchor. The tool
reports the observed range without assigning an absolute calibration, widening
coordinate limits or automatically moving any source point. Review source geometry
before correcting the reference and replay acquisition when its anchor changes.

## Shared source-image landmarks

References that never match the same animation phase may need a source-image
landmark review instead. Use a clearly shared glyph feature, such as the same
horizontal border, inside the original source pixels. Retain its measured row,
source region and the seed reference's anchor-to-landmark offset. Apply that same
offset separately to every pose; copying one canvas coordinate does not preserve
the witness when the glyph lies at a different location inside its crop.

Choose the landmark from source appearance, independently of hold-length scatter,
beat rows, receptor crossing or input association. Verify the corrected bank on
other recording intervals. This defines a consistent relative image witness; it
does not issue an independent native-center certificate or establish engine timing.
Keep the existing geometry checks and unverified-calibration warnings.
