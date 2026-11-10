# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People inspecting PIU gameplay recognition and creating independently reviewed chart intervals.

## Product Purpose

Compare the original recording, saved observations, reconstructed chart and manual interval truth.
Make recognition failures measurable without modifying native evidence.

## Operating Context

Desktop browser first, English interface, local HTTP server. Original recordings retain their
bytes and PTS. Review truth, histories, indexes, downloaded dependencies and generated assets stay
under `.local/`. The video and chart sit side by side with review details on the right.

## Capabilities and Constraints

Chart shape, weighted/nonuniform hold ticks and scroll changes are separate facts. UCS is a
limited output adapter, not the canonical model. Reviewed truth has explicit interval coverage;
outside that coverage is unreviewed. Unknown or censored endpoints remain unknown.
Automatic results and manual edits must remain distinguishable after reanalysis.
DCM supplies versioned shared editor packages built locally as tarballs from a pinned checkout.

## Product Principles

- Preserve source observations and original timestamps.
- Review bounded intervals rather than assume whole-song truth.
- Fetch bounded views, not a complete embedded report.
- Preserve explicit uncertainty and revision conflicts.
