# Play evidence inspector

Open `.local/data/SOURCE_ID/play/segment-001/report.html` locally for the **Play evidence
inspector**. This stable filename is retained for existing links. The standalone page
embeds its data and uses no external scripts, fonts or services.

The source overview at `play/index.html` reads `report-summary.json`, published
with each report from its prepared view. Rebuilding an index repairs missing or
older summaries from saved `report-data.json` without decoding or inference.
Links open saved reports, including reports with unresolved warnings.

The recording and selected note/track stay shared while switching between tabs:

| Tab | Evidence and navigation |
| --- | --- |
| Notes & judgment | Synchronized vertical SVG, target/input ranges and sustained holds; expandable note and display-refresh tables |
| Channel observations | Four independent channels on one timeline, original frame/PTS values, raw frame data and per-channel video overlays |
| Derivation | Selected track/type observations -> registered geometry and clock/beat results -> UCS availability -> timing association or held state; lazy raw JSON inspectors |
| UCS transcription | Saved UCS text, placed and unresolved rows; registration failures remain explicit |
| Warnings | Searchable diagnostic cases, selected-note scope and direct links to original frames, derived data or chart |
| Data & setup | Stage fingerprints, artifact links, coverage, timing offsets, display-latency correction and editable calibration |

Select an excluded track from the note selector or a warning to inspect its original
visible interval without inventing a target time. "Inspect observations at playback
position" anchors channel review to the current recording time; previous/next frame
buttons use retained original timestamps. Channel overlays convert normalized head
positions and native body pixels through `game_roi` into full-source coordinates.
Processing colors identify saved present/absent/unknown samples at their measured
trajectory centers, scaled from the processing channel's own coordinate height;
they do not depict the complete pixel-comparison footprint. Missing crop/source
dimensions disable overlays explicitly. Unknown channel values remain unknown.
The nearest captured frame and its distance from playback are shown, rather than
claiming a sample exists at every requested time.

Warnings are grouped first by saved note identity (including a hold's explicit
`display_note` ownership), then by check, reason and failure detail. Repeated
observations of one cause share a section with individually accessible recording
intervals. Different causes stay visible within the same note card. Exact diagnostic
copies share an observation with all source records retained. Unassigned warnings
use an explicit hold/track identity when available; temporal proximity or a shared
lane never implies ownership. Otherwise each unassigned observation stays separate.
The badge counts cases; the panel also counts causes and observations. Search matches
any original record and shows its whole case for context. Original JSON opens lazily.
Paging and search do not acknowledge or suppress warnings. Applied chart regions and effects remain inspectable separately. A warning without a recording
time exposes its diagnostic data without a fabricated seek position.

Saved UCS provenance is read during view preparation, without registering or rebuilding
a chart. Row links are enabled only when the draft's analysis hash, segment and media
identity match and the generated UCS hash is unchanged. Edited or other-source charts
remain visible but unlinked. A missing/pending draft remains unavailable; reconstructed
note targets or judgment timestamps are never presented as actual UCS placements.

Playback updates retained overlay elements and the channel cursor. It does not rebuild
observation or warning rows; a hidden note chart does not animate. Tabs support arrow,
Home and End keyboard navigation. Notes retain independent size and spacing controls.


## Refreshing the view

`just render PATH/TO/report-data.json PATH/TO/report.html` refreshes only the
standalone view. It reuses prepared data without frame decoding, OCR, chart
registration or derived analysis. Ordinary play preparation also attaches a saved
stage manifest and any existing UCS registration/text/metadata snapshot.
A saved view never reaches into another repository while rendering.

The JSON inspectors expose the existing stage records; this page does not
reconstruct missing observations or change diagnostic severity. Tests exercise
shipped browser code with synthetic observations and an observable DOM, including
shared selection, excluded-track seeks, crop transforms, UCS source linkage and
retained nodes during playback. These tests do not establish recognition accuracy.


## Type evidence and timing failures
Type presentation is independent of timing acceptance. Every retained head keeps
its type evidence and unknown reasons even if its physical or musical timing
failed. Timing exclusion cannot turn a positively identified tap into an
unconfirmed type. A genuine tap/hold contradiction remains a warning on an
excluded head as well.

Suppressed hold components keep their own native type observations separately
from the reconstructed hold interpretation. A hold's ownership claim alone
cannot remove a native tap/hold contradiction on a component. Processing-remnant
interpretations at the displayed-hold level leave original observations intact.

The chart marks a known hold without a reconstructed interval as `H`, an unknown
type as `?`, and contradictory native types as `!`. Hold geometry uncertainty is
not presented as missing type evidence.

Short holds need not expose a separate body tile. Fully qualified start/end
image comparisons contribute their declared connector rows to temporal body
support. Cap pixels and failed connector comparisons do not count as body.
Reconstruction still requires a unique pair of observed endpoints, positive
regions connected through measured source motion, and sustained multi-frame
support. Missing pixels, motion and endpoint timing remain explicit failures.

Hold connection proof keeps `observed_intervals_pixels` separate from
`occluded_intervals`, which name the foreground HUD region for each explained
hole. Original endpoint/component PTS and source frame links remain inspectable
in the derivation JSON. Positive body/tail observations after head processing
retain the proven hold identity without a fabricated head position.
