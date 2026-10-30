"""Prepare external policy and native image proofs before saved-data consumers run."""
import json

from piu_timeline.derived import call
from piu_timeline.play.observations.artifacts import cached, files, producer


def risk_proofs(data, directory):
    from piu_timeline.play.deferred_words import prepare_risk_proofs
    from piu_timeline.play.holds.input_risk import native_body_risk_available, cap_extent_spacing
    fields = ('media', 'layout', 'game_roi', 'analysis_width', 'analysis_height', 'frame_count', 'skin_detector',
              'head_registration', 'notes', 'hold_analysis', 'unsupported_intervals', 'body_risk_evidence',
              'object_interpretation', 'judgment_events', 'display_delay_correction_ms', 'median_frame_interval_seconds')
    # Verify the referenced bank before reusing any proof whose cap extent came from it.
    bank_extent = cap_extent_spacing(data) if native_body_risk_available(data) else None
    contract = {'data': {k: data[k] for k in fields if k in data}, 'verified_bank_extent': bank_extent,
                'producer': producer('play/observations/presentation.py', 'play/deferred_words.py', 'play/holds/input_risk.py',
                                     'derived/holds/risk.ts', 'derived/holds/input.ts', 'play/holds/risk_cache.py', 'play/holds/risk_ownership.py', 'play/holds/risk_evidence.py', 'play/observations/coordinates.py', 'derived/coordinates/measurements.ts', 'play/skins/held.py')}
    return cached(directory, 'risk-proofs', contract, lambda: prepare_risk_proofs(data))


def prepare(data, directory):
    from piu_timeline.play.support import visual_support
    from piu_timeline.charts.policy import attach_regions
    from piu_timeline.play.holds.input_risk import native_body_risk_available
    from piu_timeline.play.screen_regions import note_occluders
    from piu_timeline.play.object_roles import filter_frames
    from piu_timeline.play.observations.records import retained
    source = attach_regions({**data, 'visual_support': visual_support(data)}, directory)
    path = directory/'frames.jsonl'
    frames = retained(source, path)
    if path.is_file() and data.get('frame_count', len(frames)) != len(frames):
        raise ValueError('Presentation frames differ from the retained source timeline')
    native = {'native_body_risk_available': native_body_risk_available(source),
              'source_artifacts': files(directory, ('frames.jsonl', 'hold-frames.jsonl', 'judgments.jsonl', 'processing-features.npz', 'appearance-features.npz')),
              'pre_hold_proofs': risk_proofs(source, directory), 'occluders': note_occluders(source.get('layout', {})),
              'frames': [{k: f[k] for k in ('playback_seconds', 'source_pts_seconds', 'combo', 'combo_confidence') if k in f} for f in frames],
              'visibility_frames': [{k: f[k] for k in ('playback_seconds', 'source_pts_seconds', 'notes') if k in f}
                                    for f in filter_frames(source, frames)]}
    request=call('presentation.input',source,native)
    # This measurement depends on interpreted geometry and concrete motion, but
    # remains a native pixel operation rather than a report-side callback.
    interpretation=call('presentation.preview',request,str(directory))
    view=call('presentation.materialize',request,interpretation)
    pixel_path = directory/'processing-features.npz'
    if (view['scroll_pause_model'] or view['scroll_speed_model']) and pixel_path.is_file():
        from piu_timeline.play.processing import observe_processing
        inputs = call('stageInputs.processing', view)
        contract = {'input': inputs, 'files': files(directory, ('processing-features.npz', 'native-features/manifest.json')),
                    'derived': call('stageInputs.processingProducer'),
                    'producer': producer('play/observations/presentation.py', 'play/processing/__init__.py', 'play/processing/templates.py', 'play/processing/poses.py',
                                         'play/processing/motion.py', 'play/processing/passage.py')}
        def measure():
            result = observe_processing(view, pixel_path)
            for note in result['notes']:
                note['id'] = 'processing:'+str(note['note'])
            return result
        native['configured_processing'] = {'input': inputs, 'output': cached(directory, 'configured-processing', contract, measure)}
    return call('presentation.input',source,native)
