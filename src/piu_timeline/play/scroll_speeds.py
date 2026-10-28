"""TypeScript relative-speed model calculations for native processing acquisition."""
from piu_timeline.derived import call
from piu_timeline.play.scroll_pauses import model_input,position_adapter


def apply(data):
    return {**data,'scroll_speed_model':call('scroll.models',{'chart_policy':data.get('chart_policy',{})},'speed')}


def observed_path(note,data,receptor,spacing,scale):
    return position_adapter(call('scroll.speedPath',{'points':note.get('points',[])},model_input(data),receptor,spacing,scale))


def classify_warnings(data,records):
    return tuple(call('scroll.classify',model_input(data),records,'speed'))
