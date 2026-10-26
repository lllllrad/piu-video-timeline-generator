# Visual support and recording options

The current acquisition model follows notes moving upward to a fixed top
receptor. It expects approximately square white head outlines, lane-specific
blue/red/yellow interiors, and observable connections between hold caps and
bodies. Recognition of several isolated heads is insufficient to certify a
skin: every lane, tap/hold distinction and hold tail need independent support.
Skin appearance and playback options belong to the recording, not the song's
shared UCS metadata. A chart gimmick remains chart-specific.

| Appearance or option | Current scope |
| --- | --- |
| A hold tail using the same glyph as a tap | Ambiguous in a single frame; establish body connectivity and neighboring-frame continuity before treating it as a tail. Head detection success does not establish UCS suitability |
| A distinct flat, notched or illustrated endpoint | Potentially easier to separate from taps; adapt the detector and calibrate its timing anchor. Lack of an arrow-shaped tail is not evidence that the skin is visually unsuitable |
| Card faces or other heads lacking the expected contours/colors | Unsupported for UCS generation until an independent detector and hold model exist; occasional detected face details do not demonstrate support |
| A head flashing fully invisible during its approach | Unsupported for full UCS reconstruction without a verified play-option visibility model; disappearing pixels are not successful processing |
| Notes moving down toward bottom receptors | Unsupported by the current upward coordinate model; pixel detections alone do not establish tracking support |
| Hold artwork with no uniquely observable tail cap or body endpoint | Keep hold endpoints unresolved; do not emit a tap or invent a tail |

No coordinate flip, interpolation across invisible frames or relaxed color
threshold is applied implicitly. Such support needs documented geometry and
independent observations first. Judgment/combo metadata remains useful even
when a play cannot provide chart geometry.

## Recording-specific review

A local recording review can declare unsupported source-time regions in
`.local/data/<source>/visual-support.json`. This file is a review artifact,
not shared chart truth. Its `schema` is 1, `media` contains the exact recording
`size_bytes` and `mtime_ns`, and `regions` contains finite half-open
`start_seconds`/`end_seconds`, boolean `chart_geometry`, and a nonempty `reason`.
Optional evidence can name original PTS or local preview artifacts. Times remain
on the original recording timeline. Stale source identity and malformed review
records fail explicitly.

Any overlap with a region declaring `chart_geometry: false` prevents automatic
and explicit UCS registration from that analyzed range. Existing UCS files are
preserved. Reports retain raw observations and add an unsuppressible
`unsupported_visual_profile` warning and the review reason. The declaration does
not clear other warnings or establish accuracy of supported regions. Report
replay notices changed support declarations without invalidating native pixels.

## Tail review presentation

`just _visual-support --sources SOURCE_ID ...` renders the local recording reviews.
The table reports tail appearance independently of the live UCS processing gate.
It does not give a default positive classification to plays without a tail review,
or derive suitability from head detection counts. A processing block means the
current implementation cannot safely export that region; it does not imply that
a distinct tail shape is inherently hard to recognize.

The recording support file may also contain `reviews`: a list with a unique
`segment_number`, `tail_appearance` (`tap_like`, `distinct_endpoint`,
`not_observed` or `not_reviewed`), an English `observation`, and optional
`evidence` items containing a local `path` and `caption`. These descriptive
observations neither grant UCS eligibility nor suppress warnings. The generated
HTML reads the current processing regions directly, so a newly blocked play
cannot retain a stale positive label in a separate hand-maintained table.
