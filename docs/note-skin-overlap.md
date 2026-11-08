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

Only positively measured neighboring artwork and its bounded sampling influence
can exclude comparison pixels.
Unknown background, HUD rectangles and expected chart rows cannot provide such
coverage. Each recovery round uses already established foreground, so inferred
caps cannot justify one another in a circular dependency. Different role and
sampling comparisons see the same foreground before another layer is added.
Fully hidden caps cannot be reconstructed from that frame. The existing temporal
tracker can use their independently observed positions in other frames.

Resampling can mix a foreground cap into an edge pixel that matches neither
isolated reference. Preserve the positive cap footprint separately from its
possible filter influence. Fractional area sampling permits at most
`ceil(scale)` output pixels of influence; integral area sampling adds none.
Bicubic sampling uses its finite two-output-pixel stencil, widened for upscaling.
These bounds exclude contaminated pixels from a background-cap comparison;
they do not supply positive cap or body pixels. Foreground citations retain
`foreground_bounds_pixels` and `sampling_influence_pixels`. Recovery still needs
the existing visible-area, span, RGB-error and complete required-feature checks.

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

## Mixed cap boundaries

Primary cap localization uses only output pixels whose nonzero interpolation
taps belong to the declared positive cap-source footprint. Mixed boundary
pixels are checked separately as `cap_context`; a failed boundary comparison
cannot erase the independently matched interior or identify a distinct full
cap. `cap_context_qualified` and `visible_cap_runs` retain which footprint was
actually qualified. Required cap features remain independent mandatory checks.
A successful full boundary comparison can provide additional observed edge
support; an unverified boundary cannot. Body and connector regions retain
their declared context rules.

## Connector ownership

An RGB match inside another measured cap is not an independent connector.
Retain that original comparison under `connector_ownership` and compute each
cap's foreground contribution from the absolute source-kernel weights. Pixels
with more than half their weight supplied by other caps cannot provide body
evidence; negative filter coefficients cannot cancel that ownership. Mixed
pixels with a majority independent contribution still need the original RGB
comparison and spatial-cell checks. Insufficient visible support leaves the
role unknown unless separate distinct-cap artwork identifies it. Retained
positive body rows contain only the independently compared connector pixels.
This prevents a neighboring cap's colored interior from supplying an incoming
or outgoing hold connection. Transparent corners and background belong outside
the reference's positive cap footprint.

A same-lane endpoint can cover complete rows at the connector's far edge. At
least half the original connector must remain, and its remaining spatial cells
must pass unchanged. Record clipped rows without treating them as body pixels;
side-column occlusion and interior holes cannot use this edge rule.
