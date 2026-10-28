"""Native-pixel callbacks for visual trajectory models fitted in TypeScript."""
from collections import defaultdict
from piu_timeline.derived import call
from piu_timeline.play.scroll_pauses import model_input,position_adapter


def observed_paths(notes,data,receptor,spacing,scale):
    inputs={**model_input(data),'scroll_motion':data.get('scroll_motion',{})}
    fields=('lane','points','coordinate_bridge','clock_target_phase','motion_target_phase','motion_chunk',
            'timing_reconstruction','motion_clock','velocity_pixels_per_second')
    models=call('scroll.processingPaths',[{k:n[k]for k in fields if k in n}for n in notes],inputs,receptor,spacing,scale)
    chunks=defaultdict(list)
    for sample in data.get('scroll_motion',{}).get('samples',[]):chunks[sample['chunk']].append(sample)
    tables={number:(samples,[s['time']for s in samples],{s['time']:s for s in samples})for number,samples in chunks.items()}
    return [position_adapter(model,tables)for model in models]


def observed_path(note,data,receptor,spacing,scale):
    return observed_paths([note],data,receptor,spacing,scale)[0]
