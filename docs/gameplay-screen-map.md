# Phoenix gameplay screen map

Coordinates refer to the full cropped, unmirrored game image, before resizing:
x grows rightwards, y grows downwards, both normalized to 0-1. Stream overlays
outside `game_roi` are not part of the game. A manual layout overrides the
fixed profile. Unknown layouts require review; a convenient rectangle is not
proof that an overlay exists.

```text
+-------------------------------------------------------------+
| STAGE / life gauge / upper game HUD                          |
|       stationary receptors and lane-local input effects      |
|            ^ moving notes approach from below ^              |
|            |                                 |              |
|            |        judgment word            |              |
|            |           COMBO                 |              |
|            |           digits                |              |
|            |                                 |              |
|            |  tap caps / hold head-body-tail  |              |
|                   lower credit/status text                   |
+-------------------------------------------------------------+
```

## Geometry and UI footprints

| Element | Standard full-game location | Meaning for note visibility |
| --- | --- | --- |
| Stage and life gauge | Top game strip, above the receptors; exact artwork depends on mode | Not a blanket mask for the scrolling field |
| Receptor centers | y = 0.142 | Target registration row; gray outlines stay fixed while lane-local effects can flash |
| Single-left lanes | x = 0.195, 0.254, 0.313, 0.372, 0.431 | DL, UL, C, UR, DR; blue, red, yellow, red, blue |
| Single-right lanes | x = 0.570, 0.629, 0.688, 0.747, 0.806 | Same lane order/colors |
| Double lanes | x = 0.235, 0.29423, 0.35346, 0.41269, 0.47135, 0.52962, 0.58885, 0.64808, 0.7075, 0.76654 | Two panels with ten ordered lanes |
| Combo digits | `layout.combo_roi`; default centered on lane-group mean, width 0.14, y = 0.52, height 0.075 | Known foreground HUD can break a moving outline |
| COMBO caption | Centered on the digits, 1.4 times their ROI width, y = 0.475 through 0.52 | Named occluder `combo_label`; digits separately use `combo_digits` |
| Judgment word | `layout.judgment_roi` when supplied; otherwise twice the combo-digit ROI width, y = 0.385 through 0.475 for the default layout | Named occluder `judgment_word`; PERFECT/GREAT/GOOD/BAD/MISS and their animation |
| Moving field | Below receptor centers through `note_y_max`, default 0.95 | Heads normally move upwards; holds have separate head, body and tail observations |
| Credit/status text | Near the lower edge in the inspected recordings | Not automatically an occlusion exemption; actual location/overlap needs its own documented rule |
| Song/player/chart labels and grade totals | Selection, cover and result scenes, with separate metadata OCR regions | These scene-specific regions do not mask gameplay trajectories |

At a 650 x 365 analysis crop, typical lane spacing is about 38 pixels and the
receptor row is around y = 52 pixels. An ordinary cap occupies roughly one
spacing in each dimension. Actual dimensions and retained layout take precedence.
A cap's footprint, including half a spacing around its center, must intersect
one of the named HUD rectangles to explain a missing outline. Sharing the same
y coordinate in another lane does not establish occlusion. These footprints
are conservative foreground approximations, not pixel-verified HUD opacity.
The larger judgment OCR search window is independent and grants no visibility
exemption. The default word bounds include the observed Phoenix word animation;
COMBO uses a separate 1.4-times digit-ROI width at y = 0.475 through 0.52, and
digits use their own ROI. Positive matches remain usable throughout.

Positive image matches remain usable inside these rectangles. A named HUD
footprint is not proof that matched pixels are hidden. Coordinate measurements
keep their image-match and anchor-consistency requirements; rectangle overlap
alone cannot reject an otherwise valid cap measurement.

Negative evidence has a different contract. Blank bands used to prove absence
of a hold connection must be outside potential HUD coverage: foreground artwork
could conceal the body. A missing detection inside a footprint may be explained
by occlusion, but does not prove a tap, a hold endpoint or note consumption.

`screen_regions.note_occluders` supplies the named rectangles for both body
measurement and visibility diagnostics. Existing tracking reconnect tolerances
can be wider to search for a returning head; a search tolerance does not grant
an occlusion exception.

## Strict visibility and motion accounting

Every missing source frame between retained observations is checked, including
a single-frame hole in a successfully fitted or successfully timed note. A
prematurely terminated track is checked in subsequent actual source frames for
up to 650 ms or until the detector boundary. Shared peer displacement is used
when supported; bounded reappearance interpolation or a verified local approach
fit supplies an explicitly named fallback. Without motion support only the
next real source frame at the last observed location is testable. Later motion
is not invented. A detected head continuing under another track remains native
observation evidence, not proof of chart ownership.

Only intersecting named foreground HUD, the detector's receptor clipping band,
continued native detection, and a concrete applied visibility-effect handler
can account for loss. Receptor clipping begins at r + 0.85 lane spacings for
this conservative continuity check; it does not establish consumption, input
or a successful grade. A recording boundary provides no subsequent frame to
test. No frames are synthesized across it. A predicted exit from a known HUD
back into the visible field is checked again: the original mask cannot excuse
all later absence. Missing detector output and a clear pixel-verified absence
are distinct observations; a warning never claims the original note actually
vanished from the game.

Unexplained gaps and losses become `unexplained_head_detection_gap` and
`unexplained_head_disappearance`, even when timing, type or hold membership
already looks plausible. Background art, white flashes, unknown screen
visibility, fit success and a generic timing exclusion do not remove them.
Native points, missing-frame counts, original source PTS, predicted positions
and the position method remain available in `visibility-diagnostics.json` and
the report's warnings. Explained occlusions and exits are retained separately.
In particular, a gap overlapping `judgment_word`, `combo_label` or `combo_digits`
is recorded under `known_occlusions`, not emitted as a missing-head warning.
This does not turn a hidden frame into a valid shape-learning reference or
establish an input/processing time after the head leaves the HUD.

Speed changes and stops also warn by default, even when shared motion can
estimate a target. Compare adjacent four-observation windows with at least
50 ms span, accounting for regression error and two pixels of quantization per
window. Significant differences produce `scroll_speed_change` with both
measured velocities and their errors. Four or more positions staying within
0.75 pixels for at least 100 ms produce
`possible_scroll_stop_or_capture_freeze`, including the measured duration.
Ordinary short repeated render frames are insufficient. A capture freeze,
stationary false detection and actual chart stop can look alike; retain that
uncertainty instead of silently naming a verified gimmick.

Specific `note_visibility` or `scroll_motion` check exceptions require explicit
chart intervals and reasons. Timing exclusions and type exceptions cannot
silence these checks. A gimmick annotation only changes behavior through its
concrete processing handler; an unsupported annotation leaves warnings active.
Source frames and timestamps are never rewritten by this audit.

When the chart mode or player side is unknown, use independently corroborated
stationary receptor geometry or an explicit reviewed layout. Moving note
contours cannot select a layout profile.
