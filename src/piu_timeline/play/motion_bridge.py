"""Transfer a target between native coordinate blocks using independent identities."""
import numpy as np


def crossing(motion, sample, phase, error):
    positions=getattr(motion,'registered_positions',None)
    records=getattr(motion,'coordinate_registration',{}).get('chunks',[])
    if positions is None:return None
    fitted={r['chunk']:r for r in records if r.get('status')=='fitted'}
    first=fitted.get(sample['chunk'])
    if first is None:return None
    before=motion.chunks[sample['chunk']];end=before[-1]
    old={h['note']:h['offset_pixels']for h in first['head_offsets']}
    choices=[]
    for number,record in fitted.items():
        after=motion.chunks[number]
        if not 0<after[0]['time']-end['time']<=.1+1e-6:continue
        if after[0]['time']-sample['time']>.25:continue
        new={h['note']:h['offset_pixels']for h in record['head_offsets']}
        anchors=[]
        for identity in old.keys()&new.keys():
            reliable=True
            for block,offset in ((before,old[identity]),(after,new[identity])):
                observed=[(s['time'],positions[s['time']][identity][1]+s['phase']-offset)
                          for s in block if identity in positions[s['time']]]
                if (len(observed)<4 or observed[-1][0]-observed[0][0]<.065
                        or max(abs(e)for _,e in observed)>1.5):reliable=False;break
            if reliable:anchors.append(identity)
        if len(anchors)<2:continue
        shifts=np.array([old[i]-new[i]for i in anchors]);shift=float(np.median(shifts))
        if max(abs(shifts-shift))>1.:continue
        lanes={positions[s['time']][i][0]for s in before for i in anchors if i in positions[s['time']]}
        if len(lanes)<2 and max(old[i]for i in anchors)-min(old[i]for i in anchors)<=.65*motion.spacing:continue
        # Every intervening source frame needs a real observation of at least
        # one of the corroborated identities. No guessed missing-frame phase.
        middle=[s for s in motion.samples if end['time']<=s['time']<=after[0]['time']]
        previous=end['phase'];valid=True;proof=[]
        for a,b in zip(middle,middle[1:]):
            values=[old[i]-positions[b['time']][i][1]for i in anchors if i in positions[b['time']]]
            dt=b['time']-a['time']
            if (not 0<dt<=.05+1e-6 or not values or max(values)-min(values)>1.5
                    or b['chunk'] in getattr(motion,'coordinate_failures',{})):
                valid=False;break
            value=float(np.median(values))
            if not -.75<=value-previous<=30*motion.spacing*dt:valid=False;break
            previous=value;proof.append(b['source_pts'])
        if not valid or abs(previous-(after[0]['phase']+shift))>1.5:continue
        translated=phase-shift
        if not after[0]['phase']<translated<=after[-1]['phase']:continue
        result=motion.crossing(after[0],translated,error+max(.75,float(max(abs(shifts-shift)))))
        if result is None or not 0<=result['target_seconds']-sample['time']<=.25:continue
        choices.append({**result,'fit_method':'shared_scroll_registered_block_transfer',
                        'coordinate_bridge':{'from_chunk':sample['chunk'],'to_chunk':number,
                            'anchor_notes':sorted(anchors),'phase_offset_pixels':shift,
                            'maximum_anchor_disagreement_pixels':float(max(abs(shifts-shift))),
                            'intermediate_source_pts_seconds':proof},
                        'clock_target_phase':translated})
    return choices[0]if len(choices)==1 else None
