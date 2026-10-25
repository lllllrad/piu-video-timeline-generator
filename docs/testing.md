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

## What the suite establishes

| Suite | Retained checks |
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

These are contract and regression tests, not a measured corpus accuracy claim.
Synthetic frames, mocked OCR glyphs and retained observations cannot establish
the requested timing-evidence failure rate or agreement with result-grade totals.
Those require independent review of recordings and saved audit results.

## Test audit during package reorganization

The original 333 offline test methods were reviewed for observable behavior,
regression value, duplicate coverage, self-derived expected results and dependence
on incidental implementation details. The resulting suite has 325 methods.

Removed five low-value methods:

- An exact copy of `SELECTION_OFFSETS` and its parity: it tested constants rather
  than whether blinking UI is recognized. Adaptive sampling/short-result and
  bounded-read regressions remain.
- Two scalar similarity endpoints: the synthetic video detection test exercises
  matching, intervals and boundaries together.
- A checkout-local `just 1.58.0`/environment-variable checklist: it depended on an
  optional local installation and pinned its version. Config generation and
  public command execution remain covered independently of that installation.
- Clean word templates tested only against the same training images: the damaged
  word/occlusion test retains all five words and now explicitly checks a blank
  negative case; native-video integration exercises judgment use.
- A second basic summary-screen assertion: summary/result separation and spacing
  are covered in the retained scene ownership test.

Consolidated three overlapping pairs:

- Video-ID and supported URL forms share one parameterized source contract.
- Auto/fetch help smoke tests now exercise all five public command entry points
  in one method without pinning argparse prose.
- Moving a generated config is part of the alternate-checkout test, with explicit
  expected relocated paths instead of comparing against the generator itself.

Also improved retained tests: chart numeral recovery now proves both rejection
of conflicting variants and acceptance of agreeing variants, and verifies that
numeric inference was reached; spacing consensus asserts the resolved label;
standalone report layout tolerates equivalent CSS spelling. Calibration and result
reference cases moved out of the report suite. No recognition algorithm, saved
artifact version or source recording changed as part of this reorganization.
