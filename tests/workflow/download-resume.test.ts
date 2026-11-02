import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
from piu_timeline import media,workflow
results=[]
for mode in ('audio_partial','merge_pending','video_partial','video_stream_only','finished_with_streams','ordinary_cache'):
 with tempfile.TemporaryDirectory()as temporary:
  root=Path(temporary);video=root/'abc123XYZ00.f299.mp4';audio=root/'abc123XYZ00.f140.m4a'
  partial=audio.with_suffix('.m4a.part');state=audio.with_suffix('.m4a.ytdl');final=root/'abc123XYZ00.mkv'
  video.write_bytes(b'completed video bytes');original=video.stat()
  if mode=='audio_partial':partial.write_bytes(b'first audio fragments');state.write_text('{"fragment_index":793}')
  if mode=='merge_pending':audio.write_bytes(b'completed audio bytes')
  if mode=='video_partial':
   video.unlink();video.with_suffix('.mp4.part').write_bytes(b'first video fragments')
  if mode=='finished_with_streams':final.write_bytes(b'completed merged media')
  if mode=='ordinary_cache':
   video.unlink();final=root/'studio.family.mp4';final.write_bytes(b'completed studio export')
  initial_partial=partial.read_bytes()if partial.exists()else None
  initial_state=state.read_bytes()if state.exists()else None
  def resume(command):
   assert '--continue'in command and '--no-overwrites'in command
   assert command[command.index('--paths')+1]==str(root)
   if mode=='audio_partial':
    assert partial.read_bytes()==initial_partial and state.read_bytes()==initial_state
   if video.exists():assert video.read_bytes()==b'completed video bytes'and video.stat().st_mtime_ns==original.st_mtime_ns
   final.write_bytes(b'completed merged media')
   return 'PIU_FILE:'+str(final)+'\n'
  with patch.object(media,'run_download',side_effect=resume)as download:
   path,provenance=media.resolve_source('abc123XYZ00',root)
  results.append({'mode':mode,'downloads':download.call_count,'path':path.name,'network_used':provenance['network_used'],
   'video_unchanged':not video.exists()or(video.read_bytes()==b'completed video bytes'and video.stat().st_mtime_ns==original.st_mtime_ns)})
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);partial=root/'abc123XYZ00.f299.mp4';partial.write_bytes(b'only video')
 with patch.object(media,'run_download',return_value='PIU_FILE:'+str(partial)+'\n'):
  try:media.resolve_source('abc123XYZ00',root);rejected=False
  except ValueError:rejected=True
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);source=root/'abc123XYZ00';raw=source/'raw';raw.mkdir(parents=True)
 stream=raw/'abc123XYZ00.f299.mp4';stream.write_bytes(b'completed video bytes');stat=stream.stat()
 analysis=source/'analysis';analysis.mkdir();(analysis/'analysis.json').write_text(json.dumps({
  'analysis_version':workflow.ANALYSIS_VERSION,'method':'automatic_hud_ocr','segments':[],
  'provenance':{'kind':'cached_youtube'},'media':{'path':str(stream),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}}))
 with patch.object(workflow,'LOCAL_DATA',root),patch.object(workflow,'formatter',return_value=Path('unused.ts')), \
      patch.object(workflow,'resolve_source',side_effect=RuntimeError('resume requested'))as resume:
  try:workflow.run('abc123XYZ00');stale=False
  except RuntimeError as error:stale=str(error)=='resume requested'and resume.call_count==1
 print(json.dumps({'cases':results,'intermediate_marker_rejected':rejected,'stale_stream_cache_resumed':stale,
  'resumable_command':'--continue'in media.fetch_command('abc123XYZ00',root)}))
`;
const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));

test('interrupted split-stream downloads return to yt-dlp with fragments, state and finished video intact',()=>{
  for(const row of result.cases.slice(0,4)) {
    assert.equal(row.downloads,1,row.mode);
    assert.equal(row.network_used,true,row.mode);
    assert.equal(row.path,'abc123XYZ00.mkv');
    assert.equal(row.video_unchanged,true,row.mode);
  }
  assert.equal(result.resumable_command,true);
});

test('finished merged media and ordinary exports remain offline caches even beside format streams',()=>{
  for(const row of result.cases.slice(4)) {
    assert.equal(row.downloads,0,row.mode);
    assert.equal(row.network_used,false,row.mode);
    assert.equal(row.video_unchanged,true,row.mode);
  }
});

test('a downloader marker cannot promote an unmerged format stream as completed media',()=>{
  assert.equal(result.intermediate_marker_rejected,true);
  assert.equal(result.stale_stream_cache_resumed,true);
});
