# Initial validation

## Automated checks

Run `just check` offline. The suite covers environment isolation, input preparation, synthetic media probing, review validation, safe output creation, timestamp rendering, non-zero container origins, actual sampled-frame PTS, and synthetic HUD matching. Synthetic detection checks verify mechanics, not PIU accuracy.

## Real-video smoke test

Seed `_OE47GBOvB0` was downloaded with the normal fetch workflow. The merged file is 1920x1080 H.264 at a reported 60 fps; video packet timestamps cover 4088.333 playback seconds. The previously saved YouTube metadata reports 4091 seconds. This discrepancy is not evidence of a constant offset: no YouTube alignment has been asserted. The original downloaded media is left intact and ignored by Git.

The inspected layout contains a game region on the left, a separate camera region below, and chat/camera content on the right. Only the small static STAGE label in the game HUD was used for the experimental matcher (`x=180, y=0, width=76, height=20`, reference at 140 seconds). Chat and comments were not detector inputs. Default parameters over the full recording produced 15 unreviewed candidates. Result/failure screens were visually spot-checked after those candidates. This is not a measurement of precision or recall; missed sections have not been exhaustively annotated.

The first candidate was independently checked with direct frame sampling near its start and end. The HUD matcher proposed 126–260 seconds; the visual transition is bracketed by 124.7–124.8 seconds and 258.3–258.4 seconds. This demonstrates why keyframe-grid proposals must not be treated as exact boundaries. The sampled upper bounds were used to exercise the reviewed JSON/text exporter. The song and chart were read from loading/result screens, not inferred from comment labels.

Local artifacts (not committed):

- `outputs/seed-candidates.json`: all 15 unreviewed proposals and matching scores.
- `outputs/seed-results/`: post-candidate screenshots and source timestamps.
- `outputs/seed-first-fine/`: 0.1-second transition samples for the first song.
- `.local/seed-review.json`: a partial, first-song-only review.
- `outputs/seed-reviewed-sample/`: first-song JSON/text smoke-test output, on the local timeline only.

## Remaining validation and implementation

- Independently annotate all gameplay intervals, including failed/short plays and sections not proposed by the matcher. Keep this separate from comment references.
- Validate different video layouts, single/double modes, HUD skins, edits, variable frame rates, long keyframe intervals and camera-only recordings. The current template is specific to this seed layout.
- Implement song/chart OCR with uncertainty and supporting image evidence. The current matcher emits unknown song/chart values; no OCR accuracy claim is made.
- Verify local-to-YouTube alignment visually before publishing timestamps. Do not infer an offset from the duration discrepancy or silently shift the local timestamps.
- Retain unknown fields and human review until accuracy has been measured on an independent set. Chart/replay extraction remains out of scope for this milestone.
