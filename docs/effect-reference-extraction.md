# Reusable RGB effect reference extraction

This experimental tool collects repeated receptor-local RGB sequences from one
saved play and builds direction-specific candidate reference animations. It does
not publish a skin bank, change play results, or estimate physical button times.
Keep separate captures for each source/segment; similar artwork alone does not
certify the same named skin.

```sh
just _effect-capture --play .local/data/SOURCE/play/segment-001 \
  --output .local/reports/effects-SOURCE-capture --per-direction 12
just _effect-references .local/reports/effects-SOURCE-capture/capture.json \
  .local/reports/effects-SOURCE-references
```

Both destinations must be new directories under `.local/`. Open `report.html`
inside the reference destination. Inspect the original representatives alongside
the consensus and download `results.json` for every decision. Generated assets,
raw crops and capture manifests remain outside Git. Original recordings remain
unchanged.

## Responsibilities and saved evidence

Python only decodes the original recording through the existing FFmpeg adapter,
checks source PTS against retained observations, and extracts RGB and approximate
exclusion envelopes. TypeScript owns sequence alignment, eligibility, aggregation,
validation and report generation. It can rerun on saved crops without Python,
OCR, video decoding or network access. The capture's fixed 650-pixel game width
is an explicit analysis coordinate system; the recording is never retimed.

`capture.json` binds ordered frame offsets, original PTS, playback times, original
crop coordinates, source size/mtime and SHA-256 hashes of `pixels.rgb` and
`exclusions.bin`. Capture uses off-to-on receptor-light candidates, evenly sampled
within direction. These are candidate windows, not ground-truth presses. Repeated
brightening during a sustained light is not currently acquired; this sampling
bias must not be mistaken for full animation coverage.

The TypeScript loader validates hashes, dimensions, frame offsets and monotonic
PTS. Output retains input identity, implementation hashes, policy, accepted/rejected windows, per-stage
source frames, alternative alignments, visibility masks and contributor counts.
Original crops stay in the capture even when rejected for reference generation.

## Exclusion and consensus policy

The current exploratory policy is exported from
`derived/effect_references/model.ts`; its values are not calibrated confidence.

- Exclude observed note/body bounding envelopes from RGB comparisons. These are
  conservative approximate bounds, not verified opaque pixels or layer order.
- Require at least 65% jointly visible pixels in a compared stage. Reject stages
  with over 85% nearly white visible pixels because shared light gives little
  distinct appearance information.
- Fit at least five of seven marker-relative stages, with bounded temporal shifts
  and local translations. Never substitute a distant frame or silently clamp a
  missing endpoint. Keep fits within 0.005 of the best as alternatives.
- Exclude a training sequence from consensus if its mean visible RGB error exceeds
  0.10, or if fewer than five stages can be compared. Partial overlap alone does
  not discard an otherwise usable sequence.
- Require at least three accepted visible contributors at each consensus pixel.
  Unsupported pixels remain unknown and appear as checkerboard. A stage with
  insufficient supported area is not emitted as a usable candidate reference.

A median consensus can contain pixels never rendered together. The accompanying
actual representative is the closest eligible original crop; its mask and source
frame remain available. Different representatives can introduce temporal jumps.
Do not interpret checkerboard as effect transparency or reconstruct hidden pixels.

Training and evaluation use every third event within each direction as a test
candidate. Test windows sharing any source PTS with a training window are excluded
from validation. They never contribute to the seed or consensus. A low held-out
RGB residual establishes image correspondence only; phase ambiguity, renewed
flashes, unknown effect onset and unverified native occlusion remain unresolved.

## Required review

Inspect representative imagery, rejected high-error cases and unsupported stages
before reusing candidates. Compare separate videos before proposing shared banks.
Uniform white images can match even with reversed stage order; low RGB error is
not sufficient evidence for timing. Production integration still requires
onset-aware sequence validation, reliable visible-region support and independent
cross-video event tests. Skin-specific variants must remain distinct when their
images disagree.
