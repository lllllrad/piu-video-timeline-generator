"""Read saved stage/UCS provenance for the inspector, without acquisition or registration."""
from hashlib import sha256
import json
from pathlib import Path


def snapshot(data, directory):
    """Attach a bounded draft snapshot; link note IDs only to the exact source analysis."""
    directory = Path(directory)
    manifest = directory/'derived-stages'/'manifest.json'
    result = {'stages': json.loads(manifest.read_text()) if manifest.is_file() else None}
    registration = directory/'chart-registration.json'
    if not registration.is_file():
        return result
    record = json.loads(registration.read_text())
    chart = {'registration': record, 'linked': False}
    result['chart'] = chart
    if not record.get('chart'):
        return result
    path = Path(record['chart'])
    if not path.is_absolute():
        path = directory/path
    metadata_path = path.with_name('metadata.json')
    if not path.is_file() or not metadata_path.is_file():
        chart['error'] = 'Registered UCS text or metadata is unavailable'
        return result
    try:
        text = path.read_text()
        metadata = json.loads(metadata_path.read_text())
        source = metadata.get('source', {})
        # The hash also rejects changed note ordering and manual analysis edits.
        identity = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        chart['linked'] = (source.get('analysis_sha256') == identity
                           and source.get('segment_number') == data.get('segment_number')
                           and source.get('media_size_bytes') == data['media'].get('size_bytes')
                           and source.get('media_mtime_ns') == data['media'].get('mtime_ns')
                           and metadata.get('generated_ucs_sha256') == sha256(text.encode()).hexdigest())
        chart['text'] = text
        chart['metadata'] = {key: metadata[key] for key in ('identity', 'source', 'alignment', 'review_status',
                             'placements', 'unresolved', 'summary', 'hold_simplifications') if key in metadata}
    except (OSError, ValueError) as error:
        chart['error'] = f'Cannot read saved chart: {error}'
    return result
