# PIU Video Timeline Generator

YouTube timeline generator for typical Pump It Up playing video.

Detect song segments in Pump It Up gameplay recordings and produce a timeline for YouTube descriptions or comments.

## Scope and status

- First milestone: YouTube URL or local video → gameplay segment detection → song/chart recognition → timestamped text and JSON.
- Long-term goal: extract chart data and playable replays from video analysis.
- Implemented: development environment, seed manifest, yt-dlp video/metadata/comment collection, and local media inspection. **Automatic timeline detection is not implemented yet.**

## Development environment

Run from the project root on macOS/Linux:

```sh
./scripts/bootstrap
./scripts/mise exec -- just check
```

The bootstrap installs mise into `.local/bin/mise` and pinned versions of just, Python, uv, Deno, yt-dlp, and FFmpeg/ffprobe under `.local/`. Deno supports yt-dlp's YouTube JavaScript processing. Installations, caches, state, and temporary files stay inside the project; no global shell files or HOME changes are required.

Installation and YouTube access need network access and may require sandbox approval. Once installed, checks and local media processing work offline in the default sandbox. `check` includes unit tests and an integration test that generates a synthetic video and probes it.

Tool versions are pinned in `mise.toml`. To update a tool, edit its version and rerun `./scripts/bootstrap`.

### Codex command environment

Bootstrap generates a Git-ignored `.codex/config.toml` for the current checkout. It adds mise shims to PATH and sets the same local cache/install paths as `scripts/env.sh`. It disables login-shell behavior to prevent login profiles from replacing PATH. Once Codex loads this trusted project's configuration, its shell tools can run:

```sh
just --list
just check
just fetch _OE47GBOvB0 --metadata-only
just probe '/absolute/path/to/studio-download.mp4'
```

Use non-login tool calls (`login: false`). Existing sessions may retain their previous environment: reload/restart the session if `command -v just` does not resolve to this project's `.local/share/mise/shims/just`. Project configuration is ignored for untrusted projects; this setup does not change trust, sandbox, or approval policies.

The generated configuration uses absolute paths discovered at bootstrap time, not committed machine-specific paths or shell-expanded `$PATH`/`$PWD`. Run `./scripts/bootstrap` once in each fresh clone or worktree. Rerunning it is safe: unchanged generated settings can be refreshed after relocation, while customized settings are preserved and bootstrap stops with instructions for manual merging. Installed binaries may also be location-dependent; a fresh checkout and bootstrap are preferable to copying `.local/` between machines. PATH includes project tools and standard system directories.

The entire `.codex/` directory is ignored by Git. The portable generator is `scripts/configure_codex.py`; after installing tools, you can rerun it with `./scripts/mise exec -- python scripts/configure_codex.py`. Writing the protected `.codex/` directory may require approval in Codex. This does not grant broader sandbox permissions.

Outside Codex, or before configuration reload, use `./scripts/mise exec -- just ...`. The wrapper applies the local environment on every invocation, without persistent `activate` state. Avoid calling `.local/bin/mise` directly unless the project environment is already set. The just recipes delegate to this wrapper as well.

## Prepare inputs

```sh
# Inspect metadata without downloading the video.
just fetch _OE47GBOvB0 --metadata-only

# Download the best available quality using a seed ID or YouTube URL.
just fetch _OE47GBOvB0
just fetch 'https://www.youtube.com/live/uqM7H-OJp68'

# Collect reference comments separately, without downloading the video.
just fetch 5l0xgojfQGs --comments

# Inspect a YouTube Studio export without a network request.
just probe '/absolute/path/to/studio-download.mp4'
```

Videos and source metadata are stored in `data/raw/<video-id>/`; metadata containing comments is stored in `data/labels/<video-id>/`. These directories are excluded from Git. The entire seed list is never downloaded automatically. Long videos can require substantial disk space. Active livestreams are excluded; use completed VODs. Repeated downloads preserve completed files and use yt-dlp's default partial-download resume behavior.

Only download and analyze videos you own or have permission to use. Authentication or bot checks may prevent downloads; the scripts do not automatically read browser cookies. YouTube Studio exports provide a local-input alternative. Preserve the original media and timestamps without trimming or overwriting it.

## Initial dataset

Machine-readable manifest: [`data/seeds.json`](data/seeds.json). Mobile/live URLs and sharing parameters are normalized to watch URLs with the same video IDs.

| Video ID | Label status |
| --- | --- |
| [_OE47GBOvB0](https://www.youtube.com/watch?v=_OE47GBOvB0) | Unlabeled |
| [uqM7H-OJp68](https://www.youtube.com/watch?v=uqM7H-OJp68) | Unlabeled |
| [u8-FKR2E7KQ](https://www.youtube.com/watch?v=u8-FKR2E7KQ) | Unlabeled |
| [5l0xgojfQGs](https://www.youtube.com/watch?v=5l0xgojfQGs) | Approximate reference labels in comments |
| [6DqcuWMLIE4](https://www.youtube.com/watch?v=6DqcuWMLIE4) | Approximate reference labels in comments |
| [01n1Q6W0jOo](https://www.youtube.com/watch?v=01n1Q6W0jOo) | Approximate reference labels in comments |

Comments are noisy references, not ground truth. Keep them separate from detector inputs. Do not copy their timestamps or optimize for exact agreement. Evaluate timing errors, missed segments, and false detections against manually reviewed video segments; choose tolerances after inspection. If a local export and YouTube VOD have different starting points or edits, verify alignment and record offsets.

## Next milestones

1. Normalize downloads and local files into media records with duration, frame rate, timebase, and provenance.
2. Review gameplay start/end screens in representative videos and define segment boundaries.
3. Sample frames and use OCR to identify song, mode, and level candidates. Preserve uncertainty as unknown values and confidence scores.
4. Save source-relative start times and supporting evidence in JSON; render `MM:SS / H:MM:SS Song [Chart]` text.
5. Validate on a manually reviewed set independent of comments, then extend to chart/replay extraction.

## References

- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [mise installation](https://mise.jdx.dev/installing-mise.html)
- [mise directory configuration](https://mise.jdx.dev/directories.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
