/** JSON-lines transport for acquisition adapters. Algorithms are also directly importable. */
import {readSync, writeSync} from 'node:fs';
import {StringDecoder} from 'node:string_decoder';
import * as coordinateMeasurements from './coordinates/measurements.ts';
import * as skinCenters from './skins/centers.ts';
import * as skinAnchors from './skins/anchors.ts';
import * as coordinates from './beats/coordinates.ts';
import * as chords from './beats/chords.ts';
import * as domains from './beats/domains.ts';
import * as spacing from './beats/spacing.ts';
import * as phase from './beats/phase.ts';
import * as recovery from './beats/recovery.ts';
import * as validation from './beats/validation.ts';
import * as ucs from './charts/ucs.ts';
import * as transcription from './charts/transcription.ts';
import {fitGrid} from './beats/grid.ts';
import * as beats from './beats/stage.ts';
import * as stageAssociations from './stages/associations.ts';
import * as nativeTiming from './stages/native_timing.ts';
import * as stageCoordinates from './stages/coordinates.ts';

import * as registration from './registration.ts';
import * as clocks from './clocks.ts';
import * as tracks from './tracks.ts';
import * as fragments from './fragments.ts';
import * as holdMotion from './holds/image_motion.ts';
import * as holdImages from './holds/image_timing.ts';
import * as speed from './speed.ts';
import * as report from './report.ts';
import * as chartPhase from './charts/phase.ts';
import * as chartHolds from './charts/holds.ts';
import * as chartAssertions from './charts/assertions.ts';
import * as chartDraft from './charts/draft.ts';
import * as localized from './charts/localized.ts';
import * as candidates from './candidates.ts';
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
import * as holdGeometry from './holds/input.ts';
import * as holdRisk from './holds/risk.ts';
import {parseData, stringifyData} from './json.ts';

const operations = {
  coordinateMeasurements, skinAnchors, skinCenters, coordinates, chords, domains, spacing, phase, recovery, validation, ucs, transcription,
  registration, clocks, tracks, speed, report, chartPhase, chartHolds, chartAssertions, chartDraft, localized,
  holdMotion, holdImages, fragments, candidates, ranges, evidence, association, scroll, visibility, diagnostics, rowRecovery, labels, holdProjection, holdPresentation, effects, presentation, stageInputs,
  holdState, holdExtent, holdGeometry, holdRisk, stageCoordinates, nativeTiming, stageAssociations, beats: {...beats,fitGrid},
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
    const callback = request.callback ? fits => {
      send({id: request.id, kind: 'callback', fits});
      while (true) {
        const reply = receive();
        if (!reply) throw new Error('Callback transport closed');
        if (reply.kind === 'callbackResult' && reply.id === request.id) {
          if (reply.error) throw new Error(reply.error);
          return reply.value;
        }
        dispatch(reply);
      }
    } : undefined;
    const args = request.args;
    if (callback) args.push(callback);
    const result = fn(...args);
    // Mutation results are explicit at the language boundary, not shared objects.
    send({id: request.id, kind: 'result', value: result ?? null,
      mutated: request.mutated?.map(i => args[i])});
  } catch (error) {
    send({id: request.id, kind: 'error', error: String(error.message ?? error)});
  }
}
while (true) {
  const request = receive();
  if (request === null) break;
  dispatch(request);
}
