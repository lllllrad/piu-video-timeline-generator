import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import json
from piu_timeline.play.screen_regions import note_occluders,occluders_at_bounds
from piu_timeline.play.judgments import judgment_region
layout={'combo_roi':[.43,.52,.14,.075]}
print(json.dumps({'search':judgment_region(layout),'regions':note_occluders(layout),
 'old_padding':occluders_at_bounds(layout,[220,120,230,130],650,365),
 'word':occluders_at_bounds(layout,[250,148,400,164],650,365),
 'label':occluders_at_bounds(layout,[270,177,380,187],650,365),
 'digits':occluders_at_bounds(layout,[294,197,356,211],650,365)}))`;
const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('the wide OCR search window is not a note occluder',()=>{
 const word=result.regions.find(r=>r.id==='judgment_word').rect,search=result.search;
 assert.ok(word[0]>search[0]);assert.ok(word[1]>search[1]);assert.ok(word[2]<search[2]);assert.ok(word[3]<search[3]);
 assert.deepEqual(result.old_padding,[]);
});
test('word, label and digits retain their own foreground footprints',()=>{
 assert.deepEqual(result.word,['judgment_word']);assert.deepEqual(result.label,['combo_label']);
 assert.deepEqual(result.digits,['combo_digits']);
 assert.deepEqual(result.regions.map(r=>r.id),['judgment_word','combo_label','combo_digits']);
});
