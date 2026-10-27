# Non-playable artwork and native object roles

Chart metadata can declare decorative objects in a bounded part of the game
image. Interpret those source observations before building note tracks and
shared displacement, rather than treating a failed note fit as decoration.

## Metadata contract

An active `decorative_note_art` effect requires concrete `display_content`,
`note_semantics: decorative_non_playable`, `playable_notes_present: false`,
normalized `game_image_bounds` (`x, y, width, height`), song-relative start/end
times, and `boundary_uncertainty_seconds` between zero and 100 ms. The absence
of playable notes applies to this spatial and temporal scope. It must be a
chart fact supported by the recorded evidence. Artwork mixed with playable
notes in the same scope needs a more selective interpreter.

Pending and confirmed effects are active. Rejected effects restore ordinary
interpretation on the next replay. Source-bound audio alignment translates the
song interval to the current recording. Invalid metadata or unavailable
alignment fails explicitly before applying object roles.

## Per-frame interpretation

Use the original native detection and source PTS. The estimated cap footprint
extends half a lane spacing around its center. Only a footprint entirely
inside the declared rectangle, at a time inside the certain interval, receives
the `decorative_art` role. That interval excludes the effect's boundary error
and the recording alignment error at both ends.

A footprint or time overlapping the uncertain boundary remains a note
candidate and emits `decorative_art_boundary_ambiguous`. Objects outside the
scope retain their ordinary interpretation. Generic timing exceptions cannot
hide these role warnings.

Replay the remaining native candidates through the normal tracker, coordinate
registration, shared displacement and beat reconstruction. A mixed original
track can therefore split at its actual retained observations. Decorative
samples cannot anchor a shared clock, own an input refresh or generate a UCS
note. An earlier playable prefix still needs its own normal timing proof.

Body geometry uses its own measured foreground bounds in the native body-cache
coordinate system. Only fully contained body observations are separated from
hold reconstruction and cap typing. Partial or unbounded bodies keep their
original uncertainty. Receptor and popup acquisition remain independent.

## Artifacts and replay

`frames.base.jsonl`, `frames.jsonl`, `hold-frames.jsonl` and feature masks retain
all source observations. `object-interpretation.json` records each interpreted
head observation with its original PTS, frame-local detection index, lane,
full native detection and owning effect IDs. `holds.json` retains interpreted
body observations under `decorative_body_observations`. Raw channel views
continue to expose the original candidates.

Derived track indices can change when artwork is separated. They are not source
identifiers. Source time and frame-local observation identity provide the link
back to acquisition.

The interpretation contract includes the current active artwork annotations.
Editing or rejecting them invalidates derived results while reusing native
observations and pixel caches. The report verifies that its active artwork
metadata was interpreted; stale or missing interpretation becomes
`decorative_art_interpretation_missing`. An unsupported effect kind still
produces `chart_effect_handler_missing`.
