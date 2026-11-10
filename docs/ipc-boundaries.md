# Process and language boundaries

Python owns native video, image and audio acquisition and filesystem workflows.
TypeScript owns saved-data calculations. Crossing this ownership boundary still
requires process communication; a saved file avoids transmitting its contents,
but starting its consumer is also a control operation.

## Python and Node

`derived/__init__.py:call` starts one `derived/runtime.ts` worker per Python
process and reuses it. A lock permits one request at a time. A request names an
operation and its arguments; exactly one result or error completes it. Errors
never select another algorithm. There are no reverse callbacks, nested requests
or implicit updates of arguments. Where a native caller needs annotations, the
result declares them explicitly; counter alignment returns only event status and
reason alongside matches, rather than echoing the original event evidence.

The remaining uses have different inputs and reasons:

| Boundary | Call sites | Why communication remains |
| --- | --- | --- |
| Saved timing stages | `play/stages.py`, `play/beats/timing.py` | Python schedules coordinate, physical, native and musical producers. Requests carry the segment directory and small identities; TypeScript preloads stage files and writes its output. |
| Counter/judgment association | `play/associations.py`, `play/judgments.py` | Python refines acquired counter/word observations and saves `counter-input.json` or `judgment-source.json`. `associationFiles` reads the saved input and writes its result. Request construction and judgment inference remain together in TypeScript. Python loads the result once for the following native consumers. |
| Inspection and rendering | `play/observations/presentation.py`, `play/presentation.py`, `play/report.py` | Native policy/proofs and prepared source views are persisted separately. Calls pass their paths. Configured pixel processing and its input projection read `interpretation-view.json`. Rendering consumes prepared JSON; index rendering receives its entries. |
| Image localization and tracking | `play/skins/frame_centers.py`, `play/skins/coordinates.py`, `play/head_registration.py`, `play/tracking.py`, `play/observations/coordinates.py` | OpenCV/image comparisons and frame acquisition run in Python. Typed comparison records, measured positions and active tracks cross to TypeScript for coordinate qualification, projection and identity assignment. Frame batches reuse one worker; images are not sent to Node. |
| Native hold/processing measurements | `play/skins/temporal.py`, `play/skins/extents.py`, `play/processing/motion.py`, `play/holds/input_risk.py`, `play/holds/stages.py` | Python inspects masks and reference images using movement models, interval projections and sustained-state results from TypeScript. Persisted hold stages use file references; direct native fixtures use compact records. Python evaluates returned models locally while checking pixels. |
| Chart workflows and native consumer adapters | `charts/data.py`, `charts/drafts.py`, `charts/ucs.py`, `charts/policy.py`, `play/holds/analysis.py`, `tools/chart_motion.py` | Python prepares references, verifies native evidence and manages editable repository files. TypeScript supplies UCS timing/drafting/merge, policy, hold projection and speed calculations. These adapters still exchange explicit records; these workflows have not all become file-only producers. |

Python native-integration tests also invoke numerical checks on acquired image
proofs. Pure calculation tests import TypeScript directly. A test's choice of
Python does not justify a production compatibility wrapper without a caller.

This is not a claim that all remaining payloads are small. Native trajectories,
image proofs and consumer views can still be large. A file-based producer must
not be replaced by an in-memory RPC just because both APIs exist. A consumer
preloads its declared files before calculating and reuses those inputs. Numerical
calls within TypeScript use direct imports and do not cross back into Python.
See [execution contracts](analysis-stage-contracts.md).

## Other process communication

| Boundary | Location | Purpose |
| --- | --- | --- |
| FFmpeg/ffprobe pipes | `play/frames.py`, `charts/audio.py`, `tools/timeline.py`, `vision/detect.py` | Decode original media or obtain metadata and bounded audio samples. Frame pipes are acquisition streams; they are not a decoded RGB disk cache. |
| Python detection workers | `play/skins/pipeline.py` | Distribute independent native image detection across CPU workers. Each worker initializes its image bank once. At most two frames per worker are in flight; the parent retains timestamps and consumes results in submission order. `PIU_SKIN_JOBS=1` runs detection inline. |
| OCR executable on macOS | `vision/ocr.py` | Call the Swift executable that owns Apple Vision access. Linux ONNX OCR runs inside Python instead. |
| Downloader and user formats | `media.py`, `workflow.py` | Run yt-dlp and the selected Node formatter; read progress or requested text output. These are external command interfaces. |

These boundaries follow the current ownership of native libraries and filesystem
workflows. Eliminating one requires moving its owning workflow or implementing
an in-process native binding. Merely renaming a subprocess call does not remove
IPC, and moving numerical code back to Python would duplicate the implementation.
