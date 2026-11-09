"""Keep repeated frame-wide ambiguity proofs in content-addressed sidecars."""
from hashlib import sha256
import json


def presentation_source(data, directory):
    """Replace only bulky proof fields; preserve every warning and its identity."""
    evidence = directory/'evidence'/'tracking-warnings'
    saved = set()
    notes = []
    for note in data.get('notes', []):
        warnings = []
        for warning in note.get('tracking_warnings', []):
            fields = ('candidate_edges', 'candidate_frame_displacements')
            if not any(key in warning for key in fields):
                warnings.append(warning)
                continue
            encoded = json.dumps(warning, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n'
            digest = sha256(encoded.encode()).hexdigest()
            if digest not in saved:
                evidence.mkdir(parents=True, exist_ok=True)
                target = evidence/f'{digest}.json'
                if target.is_file():
                    if sha256(target.read_bytes()).hexdigest() != digest:
                        raise ValueError('Corrupt tracking-warning evidence')
                else:
                    target.write_text(encoded, encoding='utf-8')
                saved.add(digest)
            warnings.append({**{k:v for k,v in warning.items() if k not in fields},
                             'tracking_evidence': {'path': f'evidence/tracking-warnings/{digest}.json', 'sha256': digest}})
        notes.append({**note, 'tracking_warnings': warnings} if 'tracking_warnings' in note else note)
    return {**data, 'notes': notes}
