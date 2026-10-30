# Test scope and maintenance

Run the complete offline suite with `just check`. Discovery starts at `tests/`
with the checkout as its top-level directory, so every nested package is included.
Run a focused suite through the same environment, for example:

```sh
sh scripts/run.sh .venv/bin/python -m unittest tests.play.test_holds -v
```

Tests mirror the source packages. Test helpers belong in fixture modules, rather
than being imported from another test case. `tests/integration/vision_ocr.py` is
an optional host Vision run invoked by `just check-ocr`; it is deliberately not
part of offline discovery.

QG's shared `native-tests` check runs this discovery command from both `just check`
and the pre-commit hook.
The same gate checks TypeScript, bundled formats and the browser report scripts,
and runs direct TypeScript tests under `tests/derived/` with QG's native
`node-test` integration. Run `pnpm test` for the complete gate, or
`pnpm exec node --test 'tests/**/*.test.ts'` for the derived suite alone.
Python tests at the acquisition boundary call the TypeScript
implementation through the retained-data transport; they do not exercise a
separate Python fit or row-transcription implementation.

## What the suite establishes

See [recognition validation](recognition-validation.md) for the required scene
families, current gaps and synthetic-first promotion order. The suite below
contains individual protections; it is not a complete ordinary-gameplay matrix.

| Suite | Coverage |
| --- | --- |
| `metadata/` | Scene boundaries and OCR budgets, independent source-PTS consensus, title/chart ownership, credit boundaries, rival exclusion, player-separated result fields and badge recovery |
| `vision/` | OCR coordinate/preprocessing contracts, language/device/model cache dependencies, verified downloads, control crops and synthetic game-region detection |
| `play/` | Native-time geometry, occlusions and repeated renders, ambiguous association, lane-specific input evidence, hold caps and sustained state, compatible cache reuse and report behavior |
| `charts/` | Exact UCS timing, note/hold placement, collisions, ambiguous audio alignment, atomic registration, preserving edits and scoped human-authored policies |
| `workflow/` | Public command entry points, literal media path arguments, source integrity, cache promotion/failure handling and the shipped Node.js formats |
| `tools/` | Review/evaluation behavior, batch failure reporting, bootstrap recovery and preservation of user configuration |
| `integration/` | Synthetic encoded video through native decoding and note/input/hold analysis, with unchanged media bytes/timestamps and replay without decoding |

Mocks isolate unavailable host OCR, external downloads or deliberately forbidden
expensive work. A mock-call assertion is useful when it protects a requirement
such as no per-frame OCR or no repeated decoding; it should accompany an output
or state assertion. Learning a template and then recognizing the identical input
alone does not establish useful recognition coverage. Geometry tests use known
input trajectories and independently specified expected times, including negative
and ambiguous cases.

The HTML runtime harness executes the shipped JavaScript with observable DOM and
animation substitutes. It checks actual note/range output, spacing, seeking,
playback and retained geometry. It does not establish browser CSS layout or
legibility; the small desktop CSS check only verifies that the standalone report
ships its layout rules.

Contract and regression tests do not measure corpus recognition accuracy.
Timing-evidence coverage and consistency with result-grade totals require
independent review of recordings and saved analysis results.

Play maintenance tests cover source/contract invalidation, segment-lock
deferral, new-play discovery, public-command replay, failure isolation and
retry only after input changes. Audit tests retain unresolved classifications,
flag changed sources, escape report text and verify that evidence is not
rewritten. Report runtime tests execute the JavaScript embedded from the
shipped HTML/CSS/JS resources, including their standalone output.

Song-specific video observations and corpus diagnostics stay under ignored
`.local/`. Do not add recording coordinates, IDs or clip fixtures here. Tests
in this repository exercise general geometry, native-time integrity, natural
beat subdivisions, ambiguity and failure behavior using synthetic observations.
Song/chart facts belong in the separate editable UCS repository. If a reusable
artifact fits neither repository, discuss a storage location before tracking it.


`tests/derived/fixtures.ts` generates native observation records from an
independent list of expected chart times and lanes. Its stored-JSON pipeline
matrix covers triplet/quarter rhythms, simultaneous heads, close staggers,
Single/Double lane counts, three geometry sizes and 30/60/120 fps. It runs the
actual beat reconstruction and UCS timing-row transcription, asserting no lost
ordinary heads, original timestamps/positions and correct expected row times.
Unresolved close staggers must fail explicitly rather than become false chords.
Separate geometry cases retain scaled noise, contradictory references and
measurement uncertainty across JSON round trips. This validates consumption of
native observations; it does not cover arbitrary skins, image acquisition,
hold appearance or the complete four-channel evidence combination.

Stage-boundary tests execute real consumer calculations over synthetic native
records. They verify selective reuse, source-PTS and opaque-integer preservation,
full four-channel retention, explicit damaged-cache and stale-proof failure,
standalone replay without Python, and atomic output preservation on failure.
Native integration tests forbid decoding or image remeasurement when only HUD
associations change. Missing acquisition must fail before a measurement consumer
can open the video. Bulk skin/detection details are excluded from counter and
visibility consumer records.

Pure coordinate, clock, beat-domain, chord, reference-recovery, input-range and
speed, input-candidate, row/aggregate-recovery and recovered-grade regressions
run directly in TypeScript under `tests/derived/beats/` and
`tests/derived/consumers/`. Python tests exercise native image/audio acquisition,
Python object adapters, JSONL/file handling and workflow/cache integration. New
calculation regressions belong beside their TypeScript implementation; testing
the Python transport alone does not justify keeping them in Python. Ownership
tests reject foreign fields, observation edits, invalid identities and incomplete
or reordered results, alongside immutable-input checks.
