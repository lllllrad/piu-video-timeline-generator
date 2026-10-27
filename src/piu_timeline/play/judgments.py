"""Native-frame judgment words and refresh evidence independent of the counter."""
from copy import deepcopy
from bisect import bisect_left, bisect_right
from hashlib import sha256
import json
from pathlib import Path
import re

import cv2
import numpy as np

from piu_timeline.vision.ocr import ocr_images
from piu_timeline.play.frames import crop_region, decode_frames, TIME_EPSILON
from piu_timeline.play.tracking import associate
from piu_timeline.play.associations import source_assignments

from piu_timeline.play.words import LABELS, feature_map, color_mask, JudgmentReader, JudgmentTracker, EVENT_FORMAT

VERSION = 8
OBSERVATION_VERSION = 3
FEATURE_FORMAT = {'schema': 1, 'encoding': 'hue10-s90-v155-white-s70-v190'}
TEMPLATE_FORMAT = {'schema': 1, 'encoding': FEATURE_FORMAT['encoding'], 'mask': 'binary'}
LEGACY_FEATURE_FORMAT = {'schema': 1, 'encoding': 'hue10-s90-v155-white-s70-v190'}
LEGACY_TEMPLATE_FORMAT = {'schema': 1, 'encoding': 'hue10-s90-v155-white-s70-v190', 'mask': 'binary'}
OBSERVATION_FORMAT = {'schema': 1, 'reader_revision': OBSERVATION_VERSION}
ASSOCIATION_FORMAT = {'schema': 1, 'revision': 4}


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def feature_contract(data):
    layout=data.get('layout',{})
    return {'format':FEATURE_FORMAT, 'input':{key:data.get(key) for key in
            ('media','start_seconds','end_seconds','game_roi','analysis_width')},
            'region':judgment_region(layout) if 'combo_roi' in layout else None}


def cache_contracts(data, models):
    fonts=[{key:model[key] for key in ('label','hue','mask')} for model in models]
    observations={'format':OBSERVATION_FORMAT,'features':feature_contract(data),
                  'templates':fingerprint(fonts)}
    combo_matches=[{key:match.get(key) for key in ('note','combo_event','combo_lower_seconds','combo_upper_seconds')}
                   for match in source_assignments(data) if match.get('combo_event') is not None]
    association={'format':ASSOCIATION_FORMAT,'events':EVENT_FORMAT,'observations':fingerprint(observations),
                 'notes':fingerprint(data.get('notes',[])),
                 'combo_events':fingerprint(data.get('combo_events',[])),
                 'combo_matches':fingerprint(combo_matches),
                 'unsupported_intervals':fingerprint(data.get('unsupported_intervals',[])),
                 'display_delay_ms':data.get('display_delay_correction_ms',0)}
    return {'observations':observations,'association':association}


def template_document(saved):
    """Normalize an untagged legacy font file at the artifact boundary."""
    if not isinstance(saved,dict):
        return None
    if saved.get('format',LEGACY_TEMPLATE_FORMAT)!=TEMPLATE_FORMAT:
        return None
    if not isinstance(saved.get('analysis_width'),(int,float)) or saved['analysis_width']<=0:
        return None
    if not isinstance(saved.get('models'),list):
        return None
    for model in saved['models']:
        if not isinstance(model,dict) or model.get('label') not in LABELS or model.get('hue') not in range(19):
            return None
        try:
            mask=np.asarray(model['mask'])
        except (KeyError,ValueError):
            return None
        if mask.ndim!=2 or min(mask.shape)<3 or not np.isin(mask,[0,1]).all():
            return None
    return {**saved,'format':TEMPLATE_FORMAT}


def judgment_region(layout):
    if 'judgment_roi' in layout:
        return layout['judgment_roi']
    x,y,w,_ = layout['combo_roi']
    left,right = max(0,x+w/2-.19),min(1,x+w/2+.19)
    top,bottom = max(0,y-.20),min(1,y-.01)
    return [left,top,right-left,bottom-top]


def load_bank(root, record, width):
    models = []
    fingerprints = set()
    for path in sorted(root.glob('segment-*/evidence/judgments/templates.json')):
        if not re.fullmatch(r'segment-\d{3}',path.parents[2].name):
            continue
        saved = template_document(json.loads(path.read_text()))
        if saved is None or saved.get('media') != record:
            continue
        scale = width/saved['analysis_width']
        for model in saved['models']:
            if model['label'] not in LABELS:
                continue
            mask = np.asarray(model['mask'],dtype='uint8')
            if scale != 1:
                mask = cv2.resize(mask,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
            key = model['label'],model['hue'],mask.shape,mask.tobytes()
            if key in fingerprints or sum(m['label']==model['label'] for m in models)>=4:
                continue
            fingerprints.add(key)
            models.append({**model,'mask':mask.tolist()})
    return models


def cache_current(data, root, directory=None):
    models=load_bank(root,data['media'],data['analysis_width'])
    if models and directory is not None and not (directory/'evidence/judgments/templates.json').is_file():
        return False
    return data.get('judgment_cache')==cache_contracts(data,models)


def observations_current(data, root, directory):
    """Association changes can replay complete compatible word observations."""
    models=load_bank(root,data['media'],data['analysis_width'])
    if models and not (directory/'evidence/judgments/templates.json').is_file():
        return False
    return ((directory/'judgments.jsonl').is_file()
            and data.get('judgment_cache',{}).get('observations') == cache_contracts(data,models)['observations'])


def collect_features(data, output):
    directory = output/'evidence/judgments';directory.mkdir(parents=True,exist_ok=True)
    cache = directory/'features-v3.npz'
    manifest=directory/'features.json'
    expected=feature_contract(data)
    if cache.is_file():
        compatible=(json.loads(manifest.read_text())==expected if manifest.is_file()
                    else FEATURE_FORMAT==LEGACY_FEATURE_FORMAT)
        if compatible:
            with np.load(cache,allow_pickle=False) as saved:
                features,pts,times=saved['features'],saved['pts'],saved['times']
            if (features.ndim!=3 or features.dtype!=np.uint8 or pts.ndim!=1 or times.ndim!=1
                    or len(features)!=len(pts) or len(pts)!=len(times)
                    or len(times)!=data.get('frame_count',len(times))
                    or not np.isfinite(pts).all() or not np.isfinite(times).all()
                    or not (np.diff(times)>0).all() or not np.isin(features,[*range(19),255]).all()):
                raise ValueError('Invalid saved judgment pixel features')
            if not manifest.is_file():
                trace=output/'frames.jsonl'
                if trace.is_file():
                    with trace.open() as stream:
                        source=[(f['source_pts_seconds'],f['playback_seconds']) for f in map(json.loads,stream)]
                    if len(source)!=len(times) or not np.allclose(source,np.column_stack((pts,times)),rtol=0,atol=1e-6):
                        raise ValueError('Saved judgment pixel PTS differs from native observations')
                manifest.write_text(json.dumps(expected,indent=2)+'\n')
            return features,pts,times,json.loads((directory/'samples.json').read_text())
    frames,pts_values,times,samples = [],[],[],{}
    original = (output/'frames.jsonl').open()
    region = judgment_region(data['layout'])
    try:
        for pts,seconds,rgb in decode_frames(data['media'],data['start_seconds'],data['end_seconds'],
                                              data['game_roi'],data['analysis_width'],region=region):
            line = original.readline()
            if not line:
                raise ValueError('Judgment region has more frames than saved note observations')
            source = json.loads(line)
            if abs(source['source_pts_seconds']-pts)>1e-6 or abs(source['playback_seconds']-seconds)>1e-6:
                raise ValueError('Judgment region PTS differs from note observations')
            feature = feature_map(rgb)
            frames.append(feature);pts_values.append(pts);times.append(seconds)
            for hue in range(19):
                mask = color_mask(feature,hue)
                rows = np.flatnonzero(mask.sum(axis=1)>rgb.shape[1]*.10)
                if not len(rows):
                    continue
                top,bottom = int(rows[0]),int(rows[-1])+1
                cols = np.flatnonzero(mask[top:bottom].sum(axis=0)>0)
                if not len(cols):
                    continue
                width,height = int(cols[-1]-cols[0]+1),bottom-top
                if not (.20*rgb.shape[1]<width and 6<=height<.8*rgb.shape[0] and (top+bottom)/2<.80*rgb.shape[0]):
                    continue
                outside = mask[:int(.25*rgb.shape[0])].sum()+mask[int(.80*rgb.shape[0]):].sum()
                score = float(mask[top:bottom].sum()*min(1,width/max(1,3*height))
                              /(1+((height-data['analysis_width']*20/650)/5)**2)/(1+outside/max(1,mask[top:bottom].sum())))
                choices = samples.setdefault(str(hue),[])
                nearby = next((j for j,sample in enumerate(choices) if abs(seconds-sample['playback_seconds'])<.12),None)
                slot = nearby if nearby is not None else len(choices) if len(choices)<2 else min(range(2),key=lambda j:choices[j]['score'])
                if slot<len(choices) and score<=choices[slot]['score']:
                    continue
                path = directory/f'sample-{hue:02}-{slot}.png'
                cv2.imwrite(str(path),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                sample = {'file':str(path),'source_pts_seconds':pts,'playback_seconds':seconds,'hue':hue,'score':score}
                if slot<len(choices):choices[slot]=sample
                else:choices.append(sample)
        if original.readline() or len(frames)!=data['frame_count']:
            raise ValueError('Judgment region frame count differs from note observations')
    finally:
        original.close()
    # Keep every observed color family before spending the remaining budget
    # on second examples. Large blue holds must not crowd out clean words.
    first = [max(group,key=lambda sample:sample['score']) for group in samples.values()]
    second = [sample for group in samples.values() for sample in group if sample is not max(group,key=lambda item:item['score'])]
    selected = first+sorted(second,key=lambda sample:sample['score'],reverse=True)[:max(0,24-len(first))]
    features = np.asarray(frames,dtype='uint8')
    np.savez_compressed(cache,features=features,pts=np.asarray(pts_values),times=np.asarray(times))
    manifest.write_text(json.dumps(expected,indent=2)+'\n')
    (directory/'samples.json').write_text(json.dumps(selected,indent=2)+'\n')
    return features,np.asarray(pts_values),np.asarray(times),selected


def learn_models(data, output, models, samples):
    reader = JudgmentReader(models)
    selected = []
    for sample in samples:
        image = cv2.cvtColor(cv2.imread(sample['file']),cv2.COLOR_BGR2RGB)
        if reader.read(feature_map(image))['label'] is None:
            selected.append((sample,image))
    if set(LABELS).issubset({m['label'] for m in models}) and len(samples)-len(selected)>=3:
        selected=[]
    observations = []
    ocr_paths=[]
    for index,(_,image) in enumerate(selected):
        path=output/'evidence/judgments'/f'ocr-{index:02}.png'
        cv2.imwrite(str(path),cv2.cvtColor(cv2.resize(image,None,fx=3,fy=3),cv2.COLOR_RGB2BGR));ocr_paths.append(path)
    results = ocr_images(ocr_paths,english=True) if selected else []
    corroboration={}
    for (sample,_),result in zip(selected,results):
        for line in result['lines']:
            text=re.sub(r'[^A-Z]','',line['text'].upper())
            if text in LABELS and line['confidence']>=.2:
                corroboration.setdefault(text,set()).add(sample['source_pts_seconds'])
    for (sample,image),result in zip(selected,results):
        for line in result['lines']:
            label = re.sub(r'[^A-Z]','',line['text'].upper().translate(str.maketrans({'0':'O','1':'I','4':'A'})))
            label = {'MLSS':'MISS','PERFECI':'PERFECT'}.get(label,label)
            if label not in LABELS or (line['confidence']<.6 and not (line['confidence']>=.2 and len(corroboration.get(label,()))>=2)):
                continue
            crop = crop_region(image,line['box'])
            if min(crop.shape[:2])<3:
                continue
            feature = feature_map(crop)
            counts = np.bincount(feature[feature<19],minlength=19)
            hue = int(np.argmax(counts))
            mask = color_mask(feature,hue)
            ys,xs = np.nonzero(mask)
            if len(xs)<20 or len(xs)/mask.size>.85:
                continue
            mask = mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
            model = {'label':label,'hue':hue,'mask':mask.tolist(),'source_pts_seconds':sample['source_pts_seconds'],
                     'ocr_confidence':line['confidence'],'ocr_support_frames':len(corroboration.get(label,()))}
            if sum(m['label']==label for m in models)<4:
                models.append(model)
            observations.append({'sample':sample,'ocr':line})
    directory = output/'evidence/judgments'
    (directory/'bootstrap.json').write_text(json.dumps({'ocr_images':len(selected),'observations':observations,'results':[{'sample':sample,'ocr':result['lines']} for (sample,_),result in zip(selected,results)]},indent=2)+'\n')
    (directory/'templates.json').write_text(json.dumps({'format':TEMPLATE_FORMAT,'media':data['media'],'analysis_width':data['analysis_width'],'models':models})+'\n')
    return models


def synchronized_refreshes(data, events):
    """Pair mutually unique display brackets before using predicted note times."""
    links = []
    for ji,event in enumerate(events):
        if event['status']!='candidate' or event['upper_seconds']-event['lower_seconds']>.05:
            continue
        for ci,counter in enumerate(data.get('combo_events',[])):
            if counter['delta']!=1 or counter['upper_seconds']-counter['lower_seconds']>.1+TIME_EPSILON:
                continue
            if counter['status']!='matched' and counter.get('reason')!='ambiguous_note_or_combo_association':
                continue
            overlap=min(event['upper_seconds'],counter['upper_seconds'])-max(event['lower_seconds'],counter['lower_seconds'])
            distance=abs(event['upper_seconds']-counter['upper_seconds'])
            if overlap>=-1e-6 and distance<=.025:
                links.append((distance,ji,ci))
    pairs=[]
    for distance,ji,ci in links:
        alternatives=[other for other,j,c in links if (j,c)!=(ji,ci) and (j==ji or c==ci)]
        if not alternatives or min(alternatives)-distance>=.008:
            pairs.append((ji,ci))
    # Display order must agree in both channels. Conflicting pairs stay unresolved.
    return [(j,c) for j,c in pairs if all((j-j2)*(c-c2)>0 for j2,c2 in pairs if j2!=j)]


def label_counter_frames(data, observations):
    """Read labels after an already observed counter update; invent no refresh."""
    data['counter_judgment_labels']={}
    if not observations:
        return
    times=[frame['playback_seconds'] for frame in observations]
    groups={i:[] for i in range(len(data.get('combo_events', [])))}
    for match in data['matches']:
        if match['combo_event'] is not None:
            groups.setdefault(match['combo_event'],[]).append(match)
    count=0
    for ci,group in groups.items():
        event=data['combo_events'][ci]
        if event['delta']!=1 or event['upper_seconds']-event['lower_seconds']>.1+TIME_EPSILON:
            continue
        start=event['upper_seconds']
        stop=start+.050001
        if ci+1<len(data['combo_events']):
            stop=min(stop,data['combo_events'][ci+1]['lower_seconds']-1e-6)
        frames=observations[bisect_left(times,start-1e-6):bisect_right(times,stop)]
        labels={frame['label'] for frame in frames if frame['label'] is not None}
        known=[frame for frame in frames if frame['label'] is not None and frame['confidence']>=.8]
        if (len(labels)!=1 or 'MISS' in labels or len(known)<2
                or known[0]['playback_seconds']>start+.035
                or not any(b['playback_seconds']-a['playback_seconds']<=.035 for a,b in zip(known,known[1:]))
                or len({frame['source_pts_seconds'] for frame in known})<2):
            continue
        proof={'label':known[0]['label'], 'observations':[{key:frame[key] for key in
               ('source_pts_seconds','playback_seconds','label','confidence')} for frame in known]}
        data['counter_judgment_labels'][str(ci)]=proof
        for match in group:
            if match.get('judgment_label'):
                continue
            match.update(evidence_source='combo+judgment',judgment_label=known[0]['label'],
                         judgment_event=None,judgment_label_source='post_combo_frames',
                         judgment_observations=deepcopy(proof['observations']))
            count+=1
    data['coverage']['combo_frame_labeled_note_heads']=count


def merge_judgments(data, events, observations=()):
    events = deepcopy(events)
    for event in events:
        event.pop('anchor_combo_event',None)
        event.update(status=event.get('detection_status','candidate'),reason=event.get('detection_reason'))
        if event['label']=='MISS':
            event.update(status='excluded',reason='miss_is_not_a_press_timestamp')
        elif any(event['upper_seconds']>=interval['start_seconds']-.1
                 and event['lower_seconds']<=interval['end_seconds']+.1
                 for interval in data.get('unsupported_intervals',[])):
            event.update(status='excluded',reason='possible_hold_or_dense_stack')
    matches = [match for match in source_assignments(data) if match['combo_event'] is not None]
    combo_matches = list(matches)
    by_note = {match['note']:match for match in matches}
    for match in matches:
        match['evidence_source']='combo'
        match['observation_lower_seconds']=match['combo_lower_seconds']
        match['observation_upper_seconds']=match['combo_upper_seconds']
        for key in ('judgment_label','judgment_event','judgment_label_source','judgment_observations'):
            match.pop(key,None)
    counter_groups={}
    for match in matches:
        counter_groups.setdefault(match['combo_event'],[]).append(match)
    anchors=[]
    anchored_counters=set()
    for ji,ci in synchronized_refreshes(data,events):
        group=counter_groups.get(ci)
        if not group:
            continue
        event=events[ji]
        event.update(status='corroborating',reason=None,anchor_combo_event=ci)
        for match in group:
            match.update(evidence_source='combo+judgment',judgment_label=event['label'],
                         judgment_event=ji,judgment_label_source='synchronized_refresh')
        anchors.append((ji,{match['note'] for match in group}))
        anchored_counters.add(ci)
    constraints={}
    for ji,event in enumerate(events):
        if event['status']!='candidate':continue
        before=[ids for index,ids in anchors if index<ji]
        after=[ids for index,ids in anchors if index>ji]
        low=max((max(data['notes'][n]['target_seconds'] for n in ids) for ids in before),default=-float('inf'))
        high=min((min(data['notes'][n]['target_seconds'] for n in ids) for ids in after),default=float('inf'))
        constraints[ji]={n for n,note in enumerate(data['notes']) if note['status']=='estimated'
                         and low<note['target_seconds']<high}
    judge_matches = associate(data['notes'],events,display_delay=data.get('display_delay_correction_ms',0)/1000,
                              event_note_constraints=constraints)
    groups = {}
    for match in judge_matches:
        groups.setdefault(match['combo_event'],[]).append(match)
    def constituent_refresh(ci, note_ids, event):
        counter = data['combo_events'][ci]
        members = counter_groups.get(ci,[])
        if (counter.get('delta',1) <= 1 or not note_ids <= {m['note'] for m in members}
                or not 0 < counter['upper_seconds']-counter['lower_seconds'] <= .1+TIME_EPSILON):
            return False
        times = sorted(m['target_seconds'] for m in members)
        rows = []
        for time in times:
            if not rows or time-rows[-1] >= .025:
                rows.append(time)
        return (len(rows)==counter['delta']
                and event['upper_seconds'] >= counter['lower_seconds']-TIME_EPSILON
                and event['lower_seconds'] <= counter['upper_seconds']+TIME_EPSILON)
    for index,group in groups.items():
        event = events[index]
        note_ids = {match['note'] for match in group}
        conflicting = [match for match in combo_matches if match['note'] not in note_ids
                       and match['combo_event'] not in anchored_counters
                       and not constituent_refresh(match['combo_event'],note_ids,event)
                       and event['lower_seconds']-.025<=match['combo_upper_seconds']
                       and event['upper_seconds']+.025>=match['combo_lower_seconds']]
        if conflicting:
            event.update(status='excluded',reason='competing_combo_evidence')
            continue
        for match in group:
            existing = by_note.get(match['note'])
            if existing is not None:
                existing.update(evidence_source='combo+judgment',judgment_label=event['label'],judgment_event=index)
                existing['judgment_label_source']='aligned_refresh'
                event['status']='corroborating'
            else:
                match.pop('combo_event')
                match.update(combo_event=None,judgment_event=index,judgment_label=event['label'],evidence_source='judgment')
                match['observation_lower_seconds']=match.pop('combo_lower_seconds')
                match['observation_upper_seconds']=match.pop('combo_upper_seconds')
                matches.append(match)
    # A MISS is visible failure evidence, never a physical input timestamp.
    # Link only a unique previously unmatched row in a bounded delayed window.
    used = {match['note'] for match in matches}
    miss_candidates=[]
    for index,event in enumerate(events):
        if event['label']!='MISS':continue
        candidates=[i for i,note in enumerate(data['notes']) if note['status']=='estimated' and i not in used
                    and event['lower_seconds']-.25<=note['target_seconds']<=event['upper_seconds']]
        if candidates and max(data['notes'][i]['target_seconds'] for i in candidates)-min(data['notes'][i]['target_seconds'] for i in candidates)<.025:
            for note in candidates:
                miss_candidates.append({'note':note,'judgment_event':index,'label':'MISS',
                                        'status':'possible_miss','input_seconds':None})
                used.add(note)
    data['matches']=sorted(matches,key=lambda match:match['target_seconds'])
    data['judgment_events']=events
    data['miss_candidates']=miss_candidates
    data['coverage']['combo_frame_labeled_note_heads']=0
    label_counter_frames(data,observations)
    data['coverage'].update(timed_note_heads=len(matches),
                            judgment_labeled_note_heads=sum(bool(m.get('judgment_label')) for m in matches),
                            unlabeled_timed_note_heads=sum(not m.get('judgment_label') for m in matches),
                            judgment_only_note_heads=sum(m['evidence_source']=='judgment' for m in matches),
                            observed_judgment_updates=len(events),
                            observed_miss_updates=sum(e['label']=='MISS' for e in events))
    return data


def augment_judgments(data, output):
    models = load_bank(output.parent,data['media'],data['analysis_width'])
    available = {model['label'] for model in models}
    directory=output/'evidence/judgments'
    if models and set(LABELS).issubset(available):
        directory.mkdir(parents=True,exist_ok=True)
        own_fonts=directory/'templates.json'
        if not own_fonts.is_file():
            own_fonts.write_text(json.dumps({'format':TEMPLATE_FORMAT,'media':data['media'],
                                            'analysis_width':data['analysis_width'],'models':models})+'\n')
        provenance=directory/'bootstrap.json'
        if not provenance.is_file():
            provenance.write_text(json.dumps({'ocr_images':0,'method':'compatible_font_bank',
                                             'templates':fingerprint(models)})+'\n')
    trace=output/'judgments.jsonl'
    contract=cache_contracts(data,models)
    if trace.is_file() and data.get('judgment_cache',{}).get('observations')==contract['observations']:
        with trace.open() as saved:
            observations=[json.loads(line) for line in saved]
        data['judgment_analysis_version']=VERSION
        print('Reusing saved judgment observations; no decoding or OCR.',flush=True)
        tracker=JudgmentTracker()
        for observation in observations:
            tracker.update(observation['playback_seconds'],observation)
        result=merge_judgments(data,tracker.events,observations)
        result['judgment_cache']=cache_contracts(result,models)
        return result
    print('Reading native judgment words independently of combo visibility...',flush=True)
    features,pts,times,samples = collect_features(data,output)
    own_fonts=output/'evidence/judgments/templates.json'
    saved_fonts=template_document(json.loads(own_fonts.read_text())) if own_fonts.is_file() else None
    if models and (set(LABELS).issubset(available) or saved_fonts is not None and saved_fonts.get('media')==data['media']):
        print('Reusing saved color features and word templates; no decoding or OCR.',flush=True)
        data['judgment_bootstrap_ocr_images']=0
        if saved_fonts is not None:
            own_fonts.write_text(json.dumps(saved_fonts)+'\n')
    else:
        models = learn_models(data,output,models,samples)
        bootstrap=output/'evidence/judgments/bootstrap.json'
        data['judgment_bootstrap_ocr_images']=json.loads(bootstrap.read_text())['ocr_images'] if bootstrap.is_file() else 0
    reader,tracker = JudgmentReader(models),JudgmentTracker()
    with trace.open('w') as stream:
        for feature,source_pts,seconds in zip(features,pts,times):
            observation=reader.read(feature)
            tracker.update(float(seconds),observation)
            stream.write(json.dumps({'source_pts_seconds':float(source_pts),'playback_seconds':float(seconds),**observation})+'\n')
    data.update(judgment_analysis_version=VERSION,judgment_observation_version=OBSERVATION_VERSION,judgment_roi=judgment_region(data['layout']),
                judgment_template_labels=sorted({model['label'] for model in models}),
                judgment_missing_labels=sorted(set(LABELS)-{model['label'] for model in models}))
    with trace.open() as saved:
        observations=[json.loads(line) for line in saved]
    result=merge_judgments(data,tracker.events,observations)
    result['judgment_cache']=cache_contracts(result,models)
    return result
