"""Transcribe a bounded review run without publishing to the chart repository."""
from hashlib import sha256
import json

from piu_timeline.play.observations.artifacts import save_input
from piu_timeline.play.observations.inspector import snapshot


def prepare_draft(data, view, directory):
    from pathlib import Path
    from piu_timeline.charts import ucs
    from piu_timeline.charts.data import draft

    reference = json.loads((directory/'beat-reference.json').read_text())['reference']
    record = {'status': 'pending', 'reason': reference.get('reason', 'Song timing is unavailable')}
    if reference['status'] == 'available':
        try:
            template = ucs.parse(Path(reference['timing']).read_text())
            alignment = {'method': reference['alignment_method'],
                         'song_start_seconds': reference['song_start_seconds'],
                         'uncertainty_seconds': reference['alignment_uncertainty_seconds'], 'rate': 1}
            chart, evidence = draft(template, data, alignment,
                                    extend_constant_tempo=ucs.constant_tempo(template, reference['constant_tempo_bpm']),
                                    input_path=directory/'ucs-input.json')
            text = chart.text()
            (directory/'chart.ucs').write_text(text)
            media = data['media']
            source = {'analysis_sha256': sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                      'segment_number': data['segment_number'], 'media_size_bytes': media['size_bytes'],
                      'media_mtime_ns': media['mtime_ns'],
                      'playback_range': [data['start_seconds'], data['end_seconds']]}
            save_input(directory/'metadata.json', {**evidence, 'source': source, 'alignment': alignment,
                       'review_status': 'unreviewed_draft', 'generated_ucs_sha256': sha256(text.encode()).hexdigest()})
            record = {'status': 'draft', 'chart': 'chart.ucs', 'index': reference['ucs_index'],
                      'scope': 'requested_playback_window'}
        except (OSError, KeyError, ValueError) as error:
            record['reason'] = str(error)
    save_input(directory/'chart-registration.json', record)
    view['inspector_artifacts'] = snapshot(data, directory)
    save_input(directory/'report-data.json', view)
