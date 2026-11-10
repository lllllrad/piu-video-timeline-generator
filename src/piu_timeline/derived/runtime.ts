/** JSON-lines transport for acquisition adapters. Algorithms are also directly importable. */
import {readSync, writeSync} from 'node:fs';
import {StringDecoder} from 'node:string_decoder';
import * as coordinateMeasurements from './coordinates/measurements.ts';
import * as skinCenters from './skins/centers.ts';
import * as skinLocalization from './skins/localization.ts';
import * as skinAnchors from './skins/anchors.ts';
import * as skinSelection from './skins/selection.ts';
import * as coordinates from './beats/coordinates.ts';
import * as chords from './beats/chords.ts';
import * as spacing from './beats/spacing.ts';
import * as ucs from './charts/ucs.ts';
import * as stageAssociations from './stages/associations.ts';
import * as associationFiles from './stages/association_files.ts';
import * as nativeCalls from './native_calls.ts';
import * as physicalTiming from './stages/physical_timing.ts';
import * as coordinateFiles from './stages/coordinate_files.ts';
import * as timingFiles from './stages/timing_files.ts';
import * as beatFiles from './beats/files.ts';
import * as retention from './retention.ts';

import * as registration from './registration.ts';
import * as clocks from './clocks.ts';
import * as tracks from './tracks.ts';
import * as frameTracking from './frame_tracking.ts';
import * as fragments from './fragments.ts';
import * as holdMotion from './holds/image_motion.ts';
import * as holdImages from './holds/image_timing.ts';
import * as speed from './speed.ts';
import * as report from './report.ts';
import * as chartPhase from './charts/phase.ts';
import * as chartAssertions from './charts/assertions.ts';
import * as chartDraft from './charts/draft.ts';
import * as chartCombo from './charts/combo.ts';
import * as chartMerge from './charts/merge.ts';
import * as localized from './charts/localized.ts';
import * as ranges from './ranges.ts';
import * as evidence from './evidence.ts';
import * as association from './association.ts';
import * as scroll from './scroll.ts';
import * as visibility from './visibility.ts';
import * as diagnostics from './diagnostics.ts';
import * as rowRecovery from './recovery.ts';
import * as labels from './labels.ts';
import * as holdProjection from './hold_projection.ts';
import * as holdPresentation from './hold_presentation.ts';
import * as effects from './effects.ts';
import * as presentation from './pipeline/presentation.ts';
import * as stageInputs from './pipeline/inputs.ts';
import * as holdState from './hold_state.ts';
import * as holdExtent from './holds/extent.ts';
import * as holdRisk from './holds/risk.ts';
import {parseData, stringifyData} from './json.ts';

const operations = {
  coordinateMeasurements,
  skinAnchors,
  skinCenters,
  skinLocalization,
  skinSelection,
  coordinates: {prepare:coordinates.prepare},
  chords: {prepare:chords.prepare,constrain:chords.constrain},
  spacing: {registeredGap:spacing.registeredGap},
  ucs,
  retention,
  registration,
  clocks,
  tracks,
  frameTracking,
  speed,
  report: {renderFile:report.renderFile,index:report.index},
  chartPhase,
  chartAssertions,
  chartDraft,
  chartCombo,
  chartMerge,
  localized,
  holdMotion,
  holdImages: {lookupSaved:holdImages.lookupSaved,runSaved:holdImages.runSaved,projectCached:holdImages.projectCached},
  fragments,
  ranges,
  evidence,
  association: {synchronizedRefreshes:association.synchronizedRefreshes},
  scroll,
  visibility,
  diagnostics,
  rowRecovery,
  labels: {recoverPreHold:labels.recoverPreHold},
  holdProjection: {chartProjection:holdProjection.chartProjection,imageTailRoles:holdProjection.imageTailRoles},
  holdPresentation,
  effects,
  presentation: {current:presentation.current,inputFiles:presentation.inputFiles,previewFile:presentation.previewFile,prepareFile:presentation.prepareFile,materializeFiles:presentation.materializeFiles},
  stageInputs: {coordinateProducer:stageInputs.coordinateProducer,processingProducer:stageInputs.processingProducer},
  holdState,
  holdExtent,
  holdRisk,
  nativeCalls,
  coordinateFiles,
  timingFiles,
  beatFiles,
  physicalTiming: {solve:physicalTiming.solve},
  stageAssociations: {counters:stageAssociations.counters},
  associationFiles,
};
const chunk = Buffer.alloc(65536);
const decoder = new StringDecoder('utf8');
let pending = '';
function receive(): any {
  const parts = [];
  while (true) {
    const end = pending.indexOf('\n');
    if (end >= 0) {
      parts.push(pending.slice(0, end)); pending = pending.slice(end + 1);
      return parseData(parts.join(''));
    }
    if (pending) { parts.push(pending); pending = ''; }
    const count = readSync(0, chunk, 0, chunk.length, null);
    if (!count) { if (!parts.length) return null; throw new Error('Truncated analysis request'); }
    pending = decoder.write(chunk.subarray(0, count));
  }
}
function send(value: unknown): void {
  const encoded = stringifyData(value);
  const bytes = Buffer.from(encoded + '\n');
  let offset = 0;
  while (offset < bytes.length) offset += writeSync(1, bytes, offset, bytes.length - offset);
}
function dispatch(request): void {
  try {
    if (request.protocol !== 1) throw new Error('Unsupported analysis transport');
    const [module, name] = request.operation.split('.'), fn = operations[module]?.[name];
    if (typeof fn !== 'function') throw new Error(`Unknown analysis operation: ${request.operation}`);
    const args = request.args;
    const result = fn(...args);
    send({id: request.id, kind: 'result', value: result ?? null});
  } catch (error) {
    send({id: request.id, kind: 'error', error: String(error.message ?? error)});
  }
}
while (true) {
  const request = receive();
  if (request === null) break;
  dispatch(request);
}
