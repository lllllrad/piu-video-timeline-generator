// @ts-check
'use strict';
/** Presentation index only: ownership must come from saved identities, never proximity. */
function groupWarningCases(items,noteFor){
  const cases=new Map();
  for(const item of items){
    const record=item.record,note=noteFor(record);
    const key=note!==null?'note:'+note:record.hold!=null?'hold:'+record.hold:
      record.track_id!=null?'track:'+JSON.stringify([record.lane,record.track_id]):'record:'+item.id;
    let entry=cases.get(key);
    if(!entry){entry={key,note,items:[],causes:[]};cases.set(key,entry)}
    entry.items.push(item);
    const causeKey=JSON.stringify([record.check??null,record.reason??null,record.failure_detail??null]);
    let cause=entry.causes.find(candidate=>candidate.key===causeKey);
    if(!cause){cause={key:causeKey,record,items:[]};entry.causes.push(cause)}
    cause.items.push(item);
  }
  return [...cases.values()];
}
