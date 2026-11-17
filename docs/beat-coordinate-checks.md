# Independent beat coordinate checks

## Independent beat coordinate checks

Beat verification can instead establish a rhythm-to-coordinate relation from
other calibrated heads in the same fitted native block. Freeze native support
before trying phases; never feed a newly rescued pair back into its references.
Each reference needs at least four calibrated, field-visible source observations
spanning 65 ms, with native coordinate errors at most 1.5 pixels. Exclude the two
heads being checked. Require at least five other candidate heads, two lanes,
three distinct target times and 300 ms of target span, within 750 ms of the
tested targets. Their candidate beat times must explain every reference offset
within one pixel; a robust estimate does not permit discarding outliers.

Use this relation only to interpolate a pair's beat separation inside the
reference target range, with at least four actual co-observations over 65 ms
inside the original gap-check window. The candidate pair also needs calibrated
native support. Select models by those support requirements, independently of
whether their prediction passes. Every eligible block must satisfy the original
pixel-gap tolerance; do not average a conflicting prediction away. A missing
independent model leaves the existing clock-based check in force. Unverified
caps, wrong rows and nonlinear references do not acquire a convenient scale.
This check uses no input, combo, judgment, result totals or existing chart notes.
`beat-timing.json` retains successful and failed `coordinate_checks`, including
reference identities, source PTS ranges, native residuals and candidate times.
It verifies spacing, not absolute phase; bounded audio alignment and native
target intervals remain separate requirements.
