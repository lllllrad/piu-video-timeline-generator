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

QG's shared `tests` check runs this discovery command from both `just check`
and the pre-commit hook. `tests/tools/test_quality_gate.py` exercises the
installed CLI against an isolated Python suite: a failing assertion must block
the gate, and a passing assertion must allow it. The fixture does not change
the checkout's hooks or configuration.

## What the suite establishes

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
