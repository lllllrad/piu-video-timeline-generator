# PIU Video Timeline Generator

Generate a paste-ready song timeline from a Pump It Up Phoenix gameplay video.

```sh
just auto 'https://www.youtube.com/watch?v=VIDEO_ID'
```

The command downloads or opens the source, detects plays, recognizes songs, charts and result data, runs the default TypeScript format, prints the timeline, and saves everything under:

```text
.local/data/VIDEO_ID/
├── raw/
├── analysis/
│   ├── analysis.json
│   └── evidence/
└── output/
    └── default.txt
```

Local files work the same way:

```sh
just auto '/absolute/path/to/recording.mp4'
```

Local files, including YouTube Studio exports, are processed without a network request.

Download without starting analysis when needed:

```sh
just fetch 'https://www.youtube.com/watch?v=VIDEO_ID'
```

`fetch` and `auto` share the same cache. A later `auto` call reuses the completed video under `.local/data/<video-id>/raw/` without downloading it again.

Automatic OCR currently requires macOS Vision and a clearly visible Phoenix game screen. For a direct game capture or a different stream layout, specify the game rectangle:

```sh
just auto VIDEO --game-roi 0,0,1920,1080
```

## Output formats

Choose a bundled or local format with the optional second argument:

```sh
just auto VIDEO scores
```

Bundled formats live in `formats/<name>/index.ts`. Personal formats live in `.local/formats/<name>/index.ts` and take precedence over a bundled format with the same name, including `default`. A format is an ordinary Node.js TypeScript program: it receives the saved `analysis.json` path as its first argument and writes its result to stdout.

The default format produces:

```text
00:00 auto-generated timeline started
01:23 Song Name D20 start
03:45 Song Name D20 end
```

Copy [formats/default/index.ts](formats/default/index.ts) to start a new format. Shared types and helpers are in [formats/lib/timeline.ts](formats/lib/timeline.ts). See [custom formats](docs/formats.md) for examples.

Analysis is reused. Running another format for the same source does not download the video or run OCR again.

## Review before publishing

Automatic boundaries identify gameplay; they do not prove that a publication boundary is silent. Check the video and audio before publishing:

- Start on a whole second during the silent full-screen song cover.
- End on a whole second during the black transition before the score screen.
- Starting playback at either boundary must not expose another game sound effect.

Unknown or conflicting OCR values remain unknown. The project never infers a YouTube offset from a filename or modifies original media.

## Requirements

- Python 3.12
- FFmpeg and ffprobe
- Node.js 24 or newer
- `just`
- Xcode Command Line Tools on macOS for Vision OCR

Developer setup and internal commands are documented in [docs/development.md](docs/development.md). Measured behavior and known limits are in [docs/validation.md](docs/validation.md).
