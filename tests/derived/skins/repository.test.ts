import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json, tempfile
from pathlib import Path
from unittest.mock import patch
from tests.play.skins.scenes import bank_at
from piu_timeline.play.skins import repository as store
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.replay import selected_bank, selected_profile, configuration_signature
from piu_timeline.play.skins.reuse import reusable_groups
from piu_timeline.play.skins.detector import FORMAT

def rejected(action):
 try: action(); return False
 except (ValueError, FileNotFoundError): return True

with tempfile.TemporaryDirectory() as temporary:
 root=Path(temporary); repo=root/'data'; (repo/'.git').mkdir(parents=True)
 original=root/'references'; original.mkdir(); bank=bank_at(original)
 before={p.name:p.read_bytes() for p in original.iterdir()}
 (original/'unrelated-recording.mp4').write_bytes(b'not an asset')
 destination=store.publish(original/'bank.json','v1',repo)
 exact=all((destination.parent/name).read_bytes()==data for name,data in before.items())
 clean=not(destination.parent/'unrelated-recording.mp4').exists()
 same=store.publish(original/'bank.json','v1',repo)==destination
 overwrite=rejected(lambda:store.publish(original/'bank.json','v1',repo,'reviewed'))
 traversal=rejected(lambda:store.publish(original/'bank.json','../escape',repo))
 reused=sorted(reusable_groups({'skin_detector':{'bank_path':str(original/'bank.json'),
  'contract':{'bank':bank['contract'],'detector':FORMAT}}},load_bank(destination)))
 source=root/'recording';source.mkdir()
 (source/'note-skins.json').write_text(json.dumps({'schema':1,'profiles':[{'segments':[1],'bank':'old/bank.json'}]}))
 store.select('recording',[1,3],bank['skin'],'v1',repo)
 shared=store.profile_path(repo,'recording');document=json.loads(shared.read_text())
 document['profiles'][0]['role_clearance']={'model':'synthetic-gap'}
 shared.write_text(json.dumps(document))
 store.select('recording',[1,3],bank['skin'],'v1',repo)
 with patch('piu_timeline.charts.data.default_repository',return_value=repo):
  resolved=selected_bank(source,1)==str(destination)
  clearance=selected_profile(source,3)['role_clearance']=={'model':'synthetic-gap'}
  unselected=selected_bank(source,2) is None
  explicit=selected_bank(source,1,original/'bank.json')==str(original/'bank.json')
 valid=store.validate(repo)
 store.publish(original/'bank.json','v2',repo)
 store.select('recording',[3,4],bank['skin'],'v2',repo)
 remaining=json.loads(shared.read_text())['profiles']
 retained=[p['segments'] for p in remaining]==[[1],[3,4]] and remaining[0]['role_clearance']=={'model':'synthetic-gap'}
 saved_profile=shared.read_text()
 with patch('piu_timeline.charts.data.default_repository',return_value=repo):
  shared.write_text('{invalid')
  first=configuration_signature(source,1)
  shared.write_text('{changed-invalid')
  second=configuration_signature(source,1)
 shared.write_text(saved_profile)
 retry=first['profile_sha256']!=second['profile_sha256']
 store.publish(original/'bank.json','unusable',repo,'unsupported')
 unsupported=rejected(lambda:store.select('recording',[9],bank['skin'],'unusable',repo))
 manifest=destination.read_bytes();destination.write_bytes(manifest+b' ')
 with patch('piu_timeline.charts.data.default_repository',return_value=repo):
  tamper=rejected(lambda:selected_bank(source,1))
 destination.write_bytes(manifest)
 image=destination.parent/json.loads(destination.read_text())['templates'][0]['image']
 image.write_bytes(image.read_bytes()+b'changed-image-bytes')
 image_tamper=rejected(lambda:store.validate(repo))
 image.write_bytes(before[image.name])
 policy={'schema':1,'bank_contract':bank['contract'],
  'clearance':{'model':'phoenix_chromatic_gap','skin':bank['skin']}}
 roles=original/'roles.json';roles.write_text(json.dumps(policy,indent=2)+'\n')
 bound=store.publish(original/'bank.json','with-roles',repo)
 role_exact=bound.with_name('roles.json').read_bytes()==roles.read_bytes()
 role_active=store.role_model(bound)==policy['clearance']
 role_missing=rejected(lambda:store.publish(original/'bank.json','v1',repo))
 saved_roles=roles.read_bytes();roles.unlink()
 role_removed=rejected(lambda:store.publish(original/'bank.json','with-roles',repo))
 policy['bank_contract']={};roles.write_text(json.dumps(policy))
 role_stale=rejected(lambda:store.publish(original/'bank.json','stale-roles',repo))
 role_atomic=not store.bank_path(repo,bank['skin'],'stale-roles').parent.exists()
 roles.write_bytes(saved_roles)
 destination.unlink()
 with patch('piu_timeline.charts.data.default_repository',return_value=repo):
  missing=rejected(lambda:selected_bank(source,1))
 preserved=all((original/name).read_bytes()==data for name,data in before.items())
 print(json.dumps(dict(exact=exact,clean=clean,same=same,overwrite=overwrite,traversal=traversal,
  reused=reused,resolved=resolved,clearance=clearance,unselected=unselected,explicit=explicit,
  valid=valid,retained=retained,unsupported=unsupported,tamper=tamper,image_tamper=image_tamper,
  missing=missing,preserved=preserved,retry=retry,role_exact=role_exact,role_active=role_active,
  role_missing=role_missing,role_removed=role_removed,role_stale=role_stale,role_atomic=role_atomic)))
`;
const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));

test('published banks preserve reference bytes and native acquisition identity without copying unrelated media',()=>{
  assert.equal(result.exact,true);
  assert.equal(result.preserved,true);
  assert.equal(result.clean,true);
  assert.equal(result.same,true);
  assert.deepEqual(result.reused,['body/0','body/1','body/2','body/3','body/4','caps/0','caps/1','caps/2','caps/3','caps/4']);
});

test('shared segment selections resolve portable revisions and preserve independent profile settings',()=>{
  for(const key of ['resolved','clearance','unselected','explicit','retained']) assert.equal(result[key],true,key);
  assert.deepEqual(result.valid,{banks:1,sources:1});
  assert.equal(result.retry,true,'edits to a malformed shared profile invalidate a failed replay signature');
});

test('conflicting publication, escaped revisions, unsupported selections and missing or modified assets fail explicitly',()=>{
  for(const key of ['overwrite','traversal','unsupported','tamper','image_tamper','missing']) assert.equal(result[key],true,key);
});

test('publication preserves bank-bound role policy and rejects missing or stale policy revisions',()=>{
  for(const key of ['role_exact','role_active','role_missing','role_removed','role_stale','role_atomic'])
    assert.equal(result[key],true,key);
});
