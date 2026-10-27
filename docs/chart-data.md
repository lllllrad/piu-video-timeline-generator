# Editable chart data

The official [catalogue PDF](https://ucs.piugame.com/sample_download/pdf.php) identifies each song by a UCS code. A ZIP such as [CS349](https://ucs.piugame.com/sample_download/zip.php?ucs_index=CS349) supplies an empty UCS timing skeleton and reference music. The skeleton does not supply the game's note arrangement.

## Repository and workflow

```sh
just charts init
just charts list 'Switronic'
just charts add SOURCE --segment 20 --ucs-index CS306
just charts sync
just charts refresh-catalog
```

`init` creates a separate local Git repository at `../piu-chart-data`, preserving existing files. It does not publish a remote. `PIU_CHART_DATA_DIR` or the global `--repo PATH` option selects a different location. Commit and review chart edits in that repository independently of analyzer code. Its layout is:

```text
catalog.json
aliases.json
timing/CS306.ucs
charts/CS306/D22/phoenix/chart.ucs
charts/CS306/D22/phoenix/metadata.json
```

Once initialized, successful `just play` runs register missing charts automatically, including
compatible cached analyses. Registration never overwrites an existing chart directory. Download,
identity or alignment failures write a pending reason in the play's `chart-registration.json`
without invalidating its native analysis. `sync` attempts registration for completed local plays; it
does not invoke metadata OCR or acquire gameplay frames. It may download missing reference archives
and decode audio for alignment.

An exact normalized catalogue title or an explicit alias must identify one code. There is no guessed translation or fuzzy title correction. Assign a title with `just charts alias 'VIDEO TITLE' CS349`, or pass `--ucs-index` to `add`. Multiple arrangements use different mode/level directories; game updates require an explicit `--revision NAME`. A UCS code identifies a song, not a chart difficulty.

## Timing and notes

Audio alignment compares 24 frequency bands in three independent reference windows. At least two windows must have strong, unambiguous correlation and agree within 40 ms. Alignment is translation only; mismatched, repeated or missing music stays unresolved. `add --song-start SECONDS` permits an explicit reviewed origin in original local playback seconds. Source size and mtime must match saved observations before automatic audio alignment and remain unchanged afterward.

UCS `Delay` is applied in milliseconds at each section boundary, while `BPM` and `Split` determine
row duration. Subdivision expansion preserves every original row position and section duration,
including BPM changes. The draft uses the least common multiple of each original Split and 48; this
is a fine editable grid, not evidence of the intended musical subdivision. Metadata retains observed
ranges and placement residuals. Unsupported directives and overlapping timing sections require
manual handling.

Some official skeletons end before their music ends. When both the catalogue and every template
section declare the same single constant BPM, registration appends timing rows through the last
bounded observation. Original rows remain at their original times. Metadata records the extension
and requires review; variable-tempo catalogue entries are never extrapolated. Beat reconstruction uses the same
independent catalogue/template agreement to extend its derived timing extent through bounded
observations; it retains the original template and reports the provisional extension. `add --rebuild-draft`
explicitly regenerates an untouched, unreviewed UCS draft and preserves an ignored backup directory.
Reviewed charts and UCS files with human edits are refused; ordinary automatic registration never
rebuilds them.

Detected note geometry supplies chart notes independently of successful input/judgment association, so missed inputs do not remove notes from the draft. Hold-aware projection suppresses hold body/tail detections as separate taps and emits `M`/`H`/`W` cells. Single and Double use five and ten columns respectively. Conflicting same-lane placements, unbounded fits and censored hold endpoints are recorded as unresolved. The template cannot reveal notes absent from the observations.

A UCS tap also requires positive isolated-tap shape evidence. An observed hold cap
without reconstructed hold geometry, an unknown type, missing type observations,
or contradictory tap/hold evidence remains an unresolved placement. A failed hold
reconstruction never falls back to `X`. Reconstructed holds keep their endpoint
requirements and cannot override a contradictory pre-contact tap observation.
Legacy analyses without type evidence must be refreshed before exporting taps.

Generated metadata explicitly records `review_status: unreviewed_draft`, source ID/segment, source identity, analysis fingerprint, timing source/hash, alignment evidence and placements. These drafts must not validate the same recording from which they were extracted. A human can edit `chart.ucs` directly and mark metadata reviewed after independent checking. Normalized timing-template hashes identify parsed timing content, not original ZIP bytes.

## Region processing and automatic-check exceptions

Each chart's `metadata.json` can contain human-authored `regions`. Times are seconds from the reference song origin, not recording timestamps. Intervals include `start_seconds` and exclude `end_seconds`. Membership is determined by a note's head time, so a hold is handled as one note rather than independent ticks. These settings apply to association and report projection; raw native detections and original media remain intact.

```json
{
  "regions": [
    {
      "id": "nonlinear-scroll",
      "start_seconds": 42.5,
      "end_seconds": 47.25,
      "processing": "exclude_timing",
      "check_exceptions": ["timing_evidence"],
      "reason": "Extreme speed changes prevent a reliable trajectory fit.",
      "details": "Inspect the video and fill this part of the UCS manually."
    },
    {
      "id": "hold-gimmick",
      "start_seconds": 76,
      "end_seconds": 79,
      "processing": "hold_state_only",
      "check_exceptions": [],
      "reason": "Interpret this section as sustained holds rather than new tap inputs."
    }
  ]
}
```

Supported processing methods:

| Value | Behavior |
| --- | --- |
| `standard` | Keep normal association and recognition; may still declare scoped check exceptions. |
| `exclude_timing` | Keep visible notes and native observations, suppress automatic input connections for member notes. |
| `hold_state_only` | Keep reconstructed hold-state evidence; suppress discrete tap connections for member notes. |

`check_exceptions` is independent of processing.
`note_type_conflict` scopes exemptions for reviewed type transformations; `note_type_unresolved` separately scopes exemptions for unobservable types. Each requires a human-authored region containing the full evidence interval. Timing exclusions do not suppress these warnings. Source evidence and type status remain unchanged.
`timing_evidence` removes only member notes from the eligible timing-evidence check count; the unfiltered count and unresolved status remain available.
`stage_grade_totals` declares a partial exemption for that region, not proof that whole-stage grade totals agree. It never fills labels to match result quotas. A recording-specific cut or freeze should not be encoded as a permanent chart gimmick shared by every performance.

Every region needs a unique ID, bounded interval and reason. Unknown fields, invalid methods and conflicting overlapping processing rules are rejected. Overlapping standard annotations and check exceptions may be combined. Run `just charts validate` to check both UCS text and region policies; `schema.json` also supports JSON editors. Explicit draft rebuilding preserves these human-authored regions.

Every report build rereads the metadata. A verified per-recording reference-audio alignment maps
regions to original playback time; another recording never reuses the seed recording's offset.
Alignment is cached separately from frames. Invalid metadata or failed alignment is shown in the
HTML and `chart-policy.json`, without silently applying exceptions. The report's **Chart region
handling** panel lists mapped regions, reasons and seek links. `timing-ranges.json` includes
per-note policy information, unfiltered `counts`, and `eligible_counts` after scoped timing
exceptions. No automatic exception is created merely because a note failed recognition.

## Downloads

ZIPs, PDFs and music remain under `.local/cache/ucs/`; no archive member is extracted to an
archive-controlled path. Size limits and expected UCS/music members are checked, and HTML
login/error responses are rejected. HTTPS certificate and hostname verification remain enabled.
Anonymous SSO cookies are kept in memory only; one retry of the original URL handles the site's
malformed first callback. `PIU_UCS_CA_FILE` can supplement the trust chain when the server omits
intermediate certificates; a locally provisioned `intermediates.pem` in the UCS cache is also
recognized. No credentials or session cookies are stored with chart data.

## Suspected effects awaiting review

`gimmick_candidates` records suspected chart effects with song-relative bounds,
a `kind`, `reason`, `review_status` (`pending`, `confirmed`, or `rejected`) and
source evidence. Repeated pre-receptor visibility losses across independent
lanes can nominate a pending visibility modifier. Capture, overlays and layout
errors remain possible explanations; nomination is not a verified game rule.

Automatic recording preserves existing human fields, review decisions and UCS
notes. Repeated observations are deduplicated. Song bounds require an existing
verified recording-to-song translation; otherwise the candidate stays in the
local `gimmick-candidates.json` until alignment is available. Source PTS and
playback times remain separate. No recording or extracted image is copied into
the chart repository.

Pending and confirmed recognized effects apply immediately; `rejected` disables
application without deleting evidence. A visibility modifier classifies the corroborated pre-receptor losses as
`visibility_modified`, not consumption, and retains the raw samples. Timing and
type warnings remain active. No check exemption is generated. Unknown effect
kinds display a missing-handler warning.
A `suspected_multi_increment` effect records an integer `combo_increment` (2-10);
it changes counter interpretation only in its song interval, never result quotas
or independently recognized judgment grades. Reports show the provisional status
and original-video review links.

Effect processing lives in `play/gimmicks.py`, separate from generic region
exceptions. A configured simultaneous increment of exactly N can represent one
visible row only with independent lane-onset or consumption evidence and unique
motion association. The actual counter delta stays N. It does not create N
notes or spread a grade. Holds retain sustained-state semantics. Changes that
are not exactly the configured increment remain unresolved; missing refreshes
are not filled by division. All handlers operate on derived projections and
preserve the original saved channels. Review rejection disables a handler.

Native visibility and motion audits have separate scoped checks,
`note_visibility` and `scroll_motion`. Generic `exclude_timing` handling does
not suppress them. Use the concrete effect handler when observations establish
the behavior, and retain an explicit reason for any manual check exception.
See [screen positions and strict warnings](gameplay-screen-map.md).

Playback timing reconstruction compares supported video estimates with the
original timing skeleton, independently of the generated chart's note rows.
It selects natural subdivisions and requires one compatible song phase across
accepted groups. Ambiguous rows and spatial conflicts are explicit failures;
accepted notes retain their video ranges. A `timing_reconstruction` exception
is separate from generic timing-evidence exclusions. Song-specific timing facts
belong here; general algorithm tests belong in the analyzer repository.

### Explicit scroll pauses

A `scroll_pause` candidate specifies `speed_multiplier: 0`,
`pause_duration_seconds` equal to `end_seconds - start_seconds`, and
`boundary_uncertainty_seconds` between 0 and 0.1. Bounds remain song-relative;
source evidence should retain native onset/resumption brackets, stationary
lanes and evidence that the recording continued (for example changing BGA
pixels). An unchanging recording alone cannot establish a chart pause.
Active pauses cannot overlap. Pending and confirmed entries use the same
handler; rejected entries are inactive.

The handler builds a clock whose displacement is stationary inside each
configured pause. Pixel persistence can use this clock only when native
positions on both moving flanks and within the pause fit it. Contradictory or
insufficient observations remain unresolved. It never manufactures input,
judgment, chart rows or accepted chart times. Stationary observations and
zero-speed edges consistent with the configured interval appear under
`known_motion_effects`; original records remain in `native_motion_warnings`.
Other speed changes, missing notes, type conflicts and timing reconstruction
failures retain their normal warnings. The report displays the zero multiplier
and measured duration separately from generic region exceptions.
