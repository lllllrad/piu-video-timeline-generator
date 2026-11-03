/** Count owned physical timing states separately from retained diagnostics. */
import type {RecordData} from './types.ts';
export function summarize(notes:RecordData[],warnings:RecordData[]):RecordData{
 const failed=notes.filter(n=>n.timing_reconstruction?.status==='failed').length,
  restored=notes.filter(n=>n.timing_reconstruction?.status==='restored'||
   !n.timing_reconstruction&&n.status==='estimated'&&Number.isFinite(n.target_seconds)).length;
 return {status:failed||warnings.length?'failed':'restored',failed_notes:failed,restored_notes:restored,
  warning_notes:new Set(warnings.map(w=>w.note).filter(Number.isInteger)).size,warning_count:warnings.length,warnings};
}
