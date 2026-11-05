# Overlapping note observations

Acquisition first locates complete positive cap comparisons, even when their
role context is unknown. Their actual matching cap pixels can then explain
foreground coverage of another cap, in the same lane or an adjacent lane.
Visibility-weighted two-dimensional RGB comparisons propose positions; an accepted position must
match the entire remaining visible cap mask and every independently required cap feature. Required identifying features
must remain fully visible; hiding a tail border cannot create another tail in
its stem.
At least 25% of the cap's supported pixels, half its horizontal span and 20% of
its vertical span must remain visible. These are image-support requirements,
independent of pixels per game screen, chart timing and input observations.

Only positively measured neighboring artwork can hide comparison pixels.
Unknown background, HUD rectangles and expected chart rows cannot provide such
coverage. Each recovery round uses already established foreground, so inferred
caps cannot justify one another in a circular dependency. Different role and
sampling comparisons see the same foreground before another layer is added.
Fully hidden caps cannot be reconstructed from that frame. The existing temporal
tracker can use their independently observed positions in other frames.

`visible_cap_runs` records the actual 2-D compared footprint. `occlusion_evidence`
retains visible/hidden support counts and exact foreground template, lane,
position and sampling references. Coordinate and role observations retain this
proof; cap/body subfeature accounting uses only visible cap pixels. A hidden
connector or required role feature stays unavailable. Matching a visible cap does
not establish a tap or invent a hold connection. Neither detection nor a role
proof supplies a reconstructed chart time by itself.

Cap acquisition depends on the complete cap-reference set: another lane's cap
can provide foreground coverage. Changing any cap reference invalidates all cap
acquisition groups. Body-only reference changes still reuse unchanged caps;
body comparisons remain independent and cap-subfeature accounting is recomputed.

Visible-mask search shares the observed foreground weights across references.
Four correlations compute the same squared RGB error as enumerating each
position's visible pixels. Each proposed position is verified again directly
against its exact mask before becoming an observation. This is a search
optimization, with no reduced image coverage or additional error allowance.
