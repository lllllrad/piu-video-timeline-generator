# Image hold connectivity across foreground HUD

A typed start and typed end can establish one hold when every row between
them is either positively compared image support or an interior gap fully
contained by named foreground HUD on that lane. The actual observed intervals
and the named occluded intervals remain separate evidence; an occlusion never
supplies positive pixels. Both endpoint centers must have positive support.
A nearby HUD cannot explain missing body rows outside its own footprint.

The direct image proof requires four original captured endpoint pairs, no
source/playback gaps above 50 ms within its qualifying run, at least half a lane
spacing of observed forward travel at both ends, consistent endpoint separation,
and unique ownership. Duplicate rendered positions retain their original PTS;
they do not require the game to advance on every captured frame. There is no
additional 65 ms duration requirement on this already moving image proof.
Known intervening taps or competing endpoint identities refute the connection.

Once a pair is established, positive image components carrying only one of
those same native endpoint identities can extend its observed body evidence.
Each extension requires actual body support; a lone cap cannot fabricate a
body or suppress a later missing-body warning. This retains tail/body evidence
after the head reaches the receptor without inventing a new head position,
source motion or a button time. A failed endpoint clock remains a separate
timing failure. Unmeasured motion and unexplained missing pixels stay visible.

Spatial links across a named HUD join adjacent positive body components on the
same lane and source frame. They retain `occlusion_links` with the original
component identity and hidden intervals; each positive component keeps its own
unchanged bounds. This also supports holds longer than the visible field, whose
start and end never appear in one frame. Competing endpoints and observed taps
remain contradictions.

A successful tap image comparison does not prove its blank margins are visible.
The interpretation stage checks the actual compared pixels of `clear_above`
and `clear_below` against foreground HUD. Obscured negative regions yield
`skin_tap_clearance_occluded`, retaining the original full comparison and cap
position as unknown type evidence. HUD overlap of positive cap pixels alone
does not reject a tap when both negative margins remain observable. This
reuses saved comparisons without decoding or matching the recording again.
