"""Generic retained displacement for metadata-registration integration tests."""
from piu_timeline.play.registered_coordinates import FORMAT as COORDINATE_FORMAT

def scenario(ratio=2.,repeated=False):
    samples=[]
    for i in range(300):
        time=i/60;render=(i//2)*2/60 if repeated else time
        phase=240*min(render,2)+240*ratio*max(0,render-2)
        samples.append({'time':1000+time,'source_pts':9000+time,'phase':phase,'chunk':0,'support':4,'lanes':2})
    return {'analysis_width':400,'layout':{'lanes':[{'x':.2},{'x':.3}]},
            'scroll_motion':{'format':{'method':'registered_peer_displacement'},
                             'coordinate_registration':{'format':COORDINATE_FORMAT},'samples':samples}}
