# Validation and known limits

`just check` verifies input handling, safe output creation, timestamp math, non-zero container origins, sampled-frame PTS, HUD matching and refinement, OCR parsing, multi-frame agreement, player separation and workflow storage. Synthetic tests verify mechanics, not real-world PIU accuracy.

## Development recordings

Two Phoenix recordings were independently reviewed across 45 plays. The final development runs detected all reviewed plays and matched the reviewed song/chart values. This is coverage of those recordings, not a universal accuracy estimate.

Boundary refinement was generally close to the reviewed gameplay transition, but publication boundaries have a different requirement: they must fall in the specified silent cover/black-screen regions. Automatic HUD boundaries must therefore be reviewed before publication.

## Player result checks

Six inspected result screens covered right-side single/double and left-side basic/double layouts. All 42 checked numeric fields—five judgments, max combo and score per play—matched the saved OCR output. These examples informed implementation and are not an untouched benchmark.

Across a 30-play development recording, a result slot was found for 28 plays. Two failed plays retained empty result data. Some scores and max-combo values remained unknown; missing values were not converted to zero or borrowed from another player.

Genuine simultaneous two-player recordings have not been broadly validated. The synthetic OCR fixture verifies that distinct left/right values remain separate, not that every real layout is supported.

## Known limits

- Recognition targets Phoenix layouts and macOS Vision behavior.
- The game panel is not automatically localized in an arbitrary stream composition.
- Sparse HUD discovery can miss short appearances or an unseen skin.
- OCR agreement can repeat the same error and is not a calibrated probability.
- Overlays can hide song titles, charts or result values.
- Candidates with neither song nor chart evidence are rejected as detector false positives.
- Local and YouTube timelines can differ after editing; no offset is inferred.

Run `just check-ocr` and record the macOS/Vision version when comparing native OCR behavior.
