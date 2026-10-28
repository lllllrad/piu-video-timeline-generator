"""Adapters for TypeScript exclusion and unresolved-evidence diagnostics."""
from piu_timeline.derived import call


def exclusion_diagnostics(native,projected):
    fields=('notes','hold_analysis','chart_policy')
    return call('diagnostics.exclusions',{'notes':native.get('notes',[])},{k:projected[k]for k in fields if k in projected})


def recognition_diagnostics(data,ranges):
    fields=('notes','matches','conflicted_matches','chart_policy','visual_support','skin_detector',
            'start_seconds','end_seconds','object_interpretation','timing_reconstruction','beat_timing',
            'head_registration','skin_role_evidence','body_risk_evidence','visibility_diagnostics',
            'note_type_diagnostics','hold_analysis')
    source={k:data[k]for k in fields if k in data}
    source['visual_channels']={'processing':data.get('visual_channels',{}).get('processing',{})}
    return call('diagnostics.recognition',source,ranges)
