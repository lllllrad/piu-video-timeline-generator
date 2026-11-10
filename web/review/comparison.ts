import type {ReviewDocument,ReviewNote} from '@piu/chart-editor';
/** Only explicit reviewed coverage is eligible; this is a target-time comparison, not input accuracy. */
export function compareInterval(review:ReviewDocument,automatic:ReviewNote[],tolerance=.05):string{
 const covered=automatic.filter(n=>n.start_seconds!==null&&n.start_seconds>=review.coverage[0]&&n.start_seconds<review.coverage[1]);
 const truth=review.notes.filter(n=>n.start_seconds!==null),used=new Set<string>();let matched=0;
 for(const note of truth){
  const choices=covered.filter(n=>!used.has(n.id)&&n.lane===note.lane&&n.start_seconds!==null&&Math.abs(n.start_seconds-note.start_seconds!)<=tolerance).sort((a,b)=>Math.abs(a.start_seconds!-note.start_seconds!)-Math.abs(b.start_seconds!-note.start_seconds!));
  if(choices.length){used.add(choices[0].id);matched++;}
 }
 return `${matched}/${truth.length} known heads matched within ${tolerance*1000} ms; ${truth.length-matched} missing, ${covered.filter(n=>!used.has(n.id)).length} extra automatic targets. Censored heads, hold tails, ticks and input associations are not scored.`;
}
