# Reviewing play timing reports

Open a generated report after running `just play`. See [play analysis](play-analysis.md)
for acquisition, measurement assumptions and cache behavior.

## Comparing target and input ranges

The **Vertical note chart** keeps lanes in their original left-to-right order and places time from
top to bottom. Video and chart appear side by side on wide screens, with video on the left and the
chart on the right. The video stays visible while scrolling. Narrow screens stack them vertically.
**Note size** selects a square size from 8 to 64 CSS pixels (default 24), independent of spacing. If
that size would hide lanes or their timing markers, the chart reduces it to fit the available width
and labels the effective size. Resizing the window recalculates that fit. **Spacing** changes only
pixels per second (0.05x through 16x, in 0.01 steps); use the adjacent numeric field for precise
values. The view stays 680 pixels tall. All lanes fit the chart width without horizontal scrolling;
compact time labels and panel padding leave more room for the notes. Notes are filled squares in
their blue, red or yellow lane color, with a white arrow or center symbol. Square width and height
use the effective note size, independently of time spacing. Lime capped lines and midpoint dots to
the left mark fitted chart target ranges; magenta capped lines and midpoint dots to the right show
input ranges. Separate sides preserve both intervals when their times overlap. Long bodies in lane
colors and adjacent magenta recognition spans represent holds separately. Dots are interval
midpoints for orientation, never measured subframe switch times. An input above its target is
earlier and one below is later. Unconfirmed candidates are hidden in the chart by default. Show
candidate connections enables dashed links from individual notes to their eligible input ranges; no
generic candidate window is drawn. Conditional neighboring-row bounds remain table/detail evidence
and never become chart connections. Chords line up across lanes, and the selected target has a white
outline. Gray crosses enabled by the exclusion control show only track endpoints.

The green horizontal line follows video playback, pause and seeking. The chart uses presented
video-frame media timestamps when supported, with an animation-frame fallback reading the video
clock. Playback speed changes do not create an independent chart clock. All charts and the
calibration overlay use SVG, without canvas. The vertical chart retains nearby note, hold and range
elements in bounded time pages. Browser-driven CSS transform animations move the retained SVG group;
the video-frame callback updates the clock, corrects animation drift and changes pages when
necessary. Ordinary frames do not recreate note elements, timing ranges, tables or the overview.
Pause, buffering and seeking freeze or reposition the group; playback-rate changes re-anchor its
animation. Browsers without the Web Animations API update only the retained group transform. See the
[Element.animate API](https://developer.mozilla.org/en-US/docs/Web/API/Element/animate). Use the
recording-position slider to scrub and **Previous note / Next note** to inspect supported heads
including unmatched ones. Click a target or input outline to select its note and seek the recording.
The initial view opens at the first matched target (or first supported target when none match). A
five-lane chart and a ten-lane chart use the same left-to-right layout without combining players.

Select a note in the **Note timing comparison** table or lane chart to see its two ranges on the
same axis. The target range is the fitted receptor crossing plus/minus its saved prediction
uncertainty. The input estimate is the matched combo/judgment observation bracket with the selected
display-delay correction subtracted. The table uses absolute recording positions; the selected-note
plot uses milliseconds relative to the fitted crossing. Changing the correction updates input
ranges, difference intervals and plots together, without moving the target or creating new
associations. Tap connections are clipped again to the hard early/late limits at the chosen
correction.

The difference includes uncertainty on both sides: for target `[T_low, T_high]` and corrected input `[I_low, I_high]`, it is `[I_low - T_high, I_high - T_low]`. A wholly negative interval establishes an earlier estimate, a wholly positive interval a later estimate, and overlap with zero leaves that distinction unresolved. These are measurement uncertainty ranges, not game judgment windows. This also applies to the overview's offset bars.

Every supported target appears even without a uniquely matched refresh. A separate review pass uses
positive combo and non-MISS judgment refreshes within hard limits of 250 ms early and 500 ms late
around the fitted target center, after the configured display-delay correction. Prediction
uncertainty and contextual ranking offsets cannot widen these limits. Each connected range is the
intersection of its original observation bracket and this window; a bracket wholly outside the
window cannot connect. This also limits saved tap matches, conditional neighbor bounds and the
latency-slider view. Long-note sustained states keep their own duration rather than being treated as
repeated tap connections. Original observation brackets and source PTS remain unchanged in evidence;
an intersection is a conditional candidate range, not a new measured frame timestamp. The wider
search includes processing already visible in neighboring frames. Candidates must respect
already-owned refreshes and earlier/later processed rows. Counter, word and raw-reader observations
of the same refresh share one row decision. Reliable lane receptor observations reject candidates
when only another lane lights up; hold ticks require a separate receptor onset for a tap. Candidate
rows are ranked using nearby confirmed display offsets, retaining only near-ties within frame
uncertainty. This contextual ranking is not hardware latency calibration. Accepted alternatives
retain the supporting lane runs and original source PTS; rejected alternatives retain explicit
reason codes. Two neighboring rows can still be alternatives when one frame bracket cannot
distinguish them, but they are never counted as two presses. Native associations remain preserved
for audit; hold-contaminated matches are demoted in the presented tap view. Distinct ranges remain
separate alternatives (shown as a union in the table), with event IDs and exclusion reasons saved in
`timing-ranges.json`. For otherwise unresolved notes, saved native counter frames also contribute
positive changes of at most ten counts between readable frames at most one second apart, requiring
reader confidence of at least 0.8. These retain their original source PTS and remain unconfirmed
alternatives; single-frame reads never become confirmed matches. Neighboring confirmed processed
rows can also give conditional bounds across gaps of up to three seconds: these assume chart-row
input order and do not establish that the intervening note was pressed. The table labels them
explicitly. Conditional bounds appear only in the table and selected-note detail, never as magenta
input markers in the scrolling chart. A hard ownership, lane or order rejection is not replaced by a
conditional guess. If neither evidence exists, the input remains **Unconfirmed**, with the reason
retained per note. A persistent judgment word alone does not establish a new input. Possible MISS
candidates never receive press times. Shared chord and aggregate row brackets retain their original
evidence without inventing individual switch times. Excluded trajectories remain available through
the chart's exclusion control and evidence JSON, without fabricated target ranges. No tracked chart
catalog is required: original chart-file timestamps are still unavailable, and input estimates
remain display-based rather than measured physical switch times.

The raw offset contains input/render/display latency. It is not a measured physical switch time, hardware latency or game judgment-window score. A positive externally calibrated delay is subtracted with:

```sh
just play VIDEO --segment 1 --display-delay-ms 30
```

The HTML slider changes the displayed offsets only; changing associations requires rerunning the command. Median centering is relative alignment, not hardware calibration.
