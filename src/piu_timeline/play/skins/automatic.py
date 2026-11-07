"""Identify an active image bank from sparse native RGB samples; retain source-bound proof."""
from contextlib import closing
from hashlib import sha256
import fcntl
import json
from pathlib import Path

from piu_timeline.derived import call
from piu_timeline.play.frames import decode_frames
from piu_timeline.play.layout import fixed_layout,validate_layout
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector,FORMAT as DETECTOR
from piu_timeline.play.skins.repository import repository_root,bank_path,validate_bank

FORMAT={'schema':1,'method':'independent_native_skin_samples','windows':[.08,.22,.38,.54,.7,.86],'frame_gap_seconds':.08,
        'refinement_windows':[.15,.30,.46,.62,.78,.94]}


def candidates(repository=None):
    repository=repository_root(repository);manifest=repository/'skins/automatic.json'
    if not manifest.is_file():return []
    document=json.loads(manifest.read_text())
    if document.get('schema')!=1 or not isinstance(document.get('candidates'),list):
        raise ValueError('Invalid automatic skin candidate registry')
    result=[];seen=set()
    for selection in document['candidates']:
        if not isinstance(selection,dict)or set(selection)!={'skin','revision'}:
            raise ValueError('Automatic skin candidates need skin and revision')
        identity=(selection['skin'],selection['revision'])
        if identity in seen:raise ValueError('Duplicate automatic skin candidate')
        seen.add(identity)
        path=bank_path(repository,*identity);reference=validate_bank(path)
        result.append({'selection':selection,'path':str(path),'contract':reference['contract'],
                       'eligible':reference['status']!='unsupported'})
    return result


def cache_path(directory,segment):
    return Path(directory)/'play/skin-selections'/f'segment-{segment:03}.json'


def context(document,number,options):
    record=document['media'];stat=Path(record['path']).stat()
    if (stat.st_size,stat.st_mtime_ns)!=(record['size_bytes'],record['mtime_ns']):
        raise ValueError('Source identity changed before automatic skin selection; run just auto again')
    segment=document['segments'][number-1]
    layout=options.get('layout')or fixed_layout(segment,options.get('player'))
    if layout is None:raise ValueError('Automatic skin selection needs a known lane layout or --layout')
    return {'media':record,'game_roi':document['game_roi'],'start_seconds':segment['start_seconds'],
            'end_seconds':segment['end_seconds'],'analysis_width':options.get('width',650),
            'layout':validate_layout(layout)}


def contract(document,number,options,banks):
    return {'format':FORMAT,'policy':call('skinSelection.policy'),
            'detector':DETECTOR,'source':context(document,number,options),'candidates':banks}


def load_saved(directory,number,document,options,banks):
    path=cache_path(directory,number)
    if not path.is_file():return None
    saved=json.loads(path.read_text())
    expected=contract(document,number,options,banks)
    # Sampling plans describe acquisition; the decision depends on the actual
    # retained image observations and their source/detector/policy/bank binding.
    if ({k:v for k,v in saved.get('contract',{}).items()if k!='format'}
            !={k:v for k,v in expected.items()if k!='format'}):return None
    if saved.get('decision')!=call('skinSelection.choose',saved['candidates'],saved['contract']['policy']):
        raise ValueError('Automatic skin decision differs from its retained image evidence')
    if saved['decision']['status']!='selected'and saved['contract'].get('format')!=FORMAT:return None
    return saved


def retained(directory,number,options=None):
    if not cache_path(directory,number).is_file():return None
    document=json.loads((Path(directory)/'analysis/analysis.json').read_text())
    saved=load_saved(directory,number,document,options or {},candidates())
    if not saved or saved['decision']['status']!='selected':return None
    selection=saved['decision']['selection']
    return next(bank['path']for bank in saved['contract']['candidates']if bank['selection']==selection and bank['eligible'])


def signature(directory,number):
    path=cache_path(directory,number)
    return {'format':FORMAT,'policy':call('skinSelection.policy'),'detector':DETECTOR,
            'candidates':candidates(),'evidence_sha256':sha256(path.read_bytes()).hexdigest()if path.is_file()else None}


def reselect_saved(path,binding):
    """Selection policy consumes saved comparisons, never new image evidence."""
    if not path.is_file():return None
    saved=json.loads(path.read_text());prior=saved.get('contract',{})
    acquisition=lambda c:{k:v for k,v in c.items()if k not in ('format','policy')}
    if acquisition(prior)!=acquisition(binding)or prior.get('policy')==binding['policy']or 'format'not in prior:return None
    if saved['decision']!=call('skinSelection.choose',saved['candidates'],prior['policy']):
        raise ValueError('Automatic skin decision differs from its declared retained image evidence')
    decision=call('skinSelection.choose',saved['candidates'],binding['policy'])
    if decision['status']!='selected':return None
    return {**saved,'contract':{**binding,'format':prior['format']},'decision':decision}


def prepare(directory,number,document,options,retry=False):
    banks=candidates()
    if not any(b['eligible']for b in banks):
        raise ValueError('Image note-skin bank required: no active automatic candidates; use just skins select or --note-skin')
    path=cache_path(directory,number);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        saved=None if retry else load_saved(directory,number,document,options,banks)
        if saved is None and not retry:
            binding=contract(document,number,options,banks)
            saved=reselect_saved(path,binding)
            if saved is not None:
                if context(document,number,options)!=binding['source']or candidates()!=banks:
                    raise ValueError('Automatic skin source or reference images changed during policy evaluation')
                from piu_timeline.charts.official import write_json
                write_json(path,saved)
                print('Reusing independent skin comparisons under the current selection policy.',flush=True)
        if saved is None:
            binding=contract(document,number,options,banks);source=binding['source']
            width=source['analysis_width'];height=round(width*source['game_roi'][3]/source['game_roi'][2])
            detectors=[(b,SkinDetector(load_bank(b['path']),source['layout'],width,height))for b in banks if b['eligible']]
            measured=[{**b,'observations':[]}for b,_ in detectors];samples=[];seen=set()
            print('Identifying note skin from independent native image samples...',flush=True)
            decision=None
            for offset,fractions in [(0,FORMAT['windows']),(len(FORMAT['windows']),FORMAT['refinement_windows'])]:
                if decision is not None and decision.get('reason')!='insufficient_skin_image_support':break
                for window,fraction in enumerate(fractions,offset):
                    start=source['start_seconds']+(source['end_seconds']-source['start_seconds'])*fraction
                    end=min(source['end_seconds'],start+.14);last=None
                    sampled=decode_frames(source['media'],start,end,source['game_roi'],width)
                    with closing(sampled)as frames:
                        for pts,time,rgb in frames:
                            if last is not None and time-last<FORMAT['frame_gap_seconds']-1e-6:continue
                            digest=sha256(rgb.tobytes()).hexdigest()
                            if digest in seen:continue
                            seen.add(digest);last=time
                            samples.append({'window':window,'source_pts_seconds':pts,'playback_seconds':time,'rgb_sha256':digest})
                            for record,(_,detector)in zip(measured,detectors,strict=True):
                                record['observations'].extend({**o,'window':window,'source_pts_seconds':pts,'playback_seconds':time}
                                                              for o in detector.detect(rgb)if o['template_role']!='hold_body')
                decision=call('skinSelection.choose',measured,binding['policy'])
            if context(document,number,options)!=source or candidates()!=banks:
                raise ValueError('Automatic skin source or reference images changed during sampling')
            saved={'contract':binding,'samples':samples,'candidates':measured,'decision':decision}
            from piu_timeline.charts.official import write_json
            write_json(path,saved)
        decision=saved['decision']
        if decision['status']!='selected':
            raise ValueError('Automatic skin selection failed: '+decision['reason']+'; evidence: '+str(path))
        selected=decision['selection']
        result=next(b['path']for b in banks if b['selection']==selected)
        print('Note skin: '+selected['skin']+'/'+selected['revision']+' (automatic image evidence)',flush=True)
        return result
