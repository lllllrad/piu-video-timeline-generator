"""Apply a selected RGB image bank while preserving source counter observations."""
import json
from hashlib import sha256
import math
from pathlib import Path
import shutil
from itertools import zip_longest
from contextlib import closing, nullcontext

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.skins.bank import load_bank, ROLES
from piu_timeline.play.skins.detector import FORMAT, SkinDetector
from piu_timeline.play.skins.held import FORMAT as HELD_FORMAT, BodyAtReceptor
from piu_timeline.play.skins.pipeline import classified_frames


def detector_contract(path):
    return None if path is None else {'bank': load_bank(path)['contract'], 'detector': FORMAT, 'held_body':HELD_FORMAT}


def detector_metadata(path, bank=None):
    bank = bank or load_bank(path)
    represented = {(t['lane_kind'], t['role']) for t in bank['templates']
                   if t['role']!='tap' or t['tap_clearance']}
    return {'contract': {'bank': bank['contract'], 'detector': FORMAT, 'held_body':HELD_FORMAT},
            'bank_path': str(Path(path).resolve()), 'registration_reviewed': False,
            'reference_images': len(bank['templates']),
            'registered_native_cap_templates':len(bank['anchor_registrations']),
            'missing_template_roles': [{'lane_kind': lane, 'role': role}
                                       for lane in range(5) for role in ROLES if (lane, role) not in represented]}


def selected_profile(directory,segment):
    path = directory / 'note-skins.json'
    if not path.is_file():
        return None
    document = json.loads(path.read_text())
    if document.get('schema') != 1:
        raise ValueError('Unsupported source note-skin selection schema')
    matches = [p for p in document['profiles'] if segment in p['segments']]
    if len(matches) > 1:
        raise ValueError('More than one note skin is selected for this play')
    return matches[0]if matches else None


def selected_bank(directory, segment, explicit=None):
    if explicit is not None:return str(Path(explicit).resolve())
    profile=selected_profile(directory,segment)
    return str((directory/profile['bank']).resolve())if profile else None


def configuration_signature(directory,segment):
    """Retry failed work when selected configuration or reference bytes change."""
    path=directory/'note-skins.json'
    try:
        profile=selected_profile(directory,segment)
        bank=selected_bank(directory,segment)
        return {'profile':profile,'bank_path':bank,'detector':detector_contract(bank)}
    except (OSError,ValueError,KeyError)as error:
        try:digest=sha256(path.read_bytes()).hexdigest()
        except OSError:digest=None
        return {'profile_sha256':digest,'error':type(error).__name__+': '+str(error)}


def configuration_current(data,directory,segment):
    """Check persisted selection independently of acquired frame observations."""
    bank=selected_bank(directory,segment)
    if data.get('skin_detector',{}).get('contract')!=detector_contract(bank):return False
    if bank is not None and data['skin_detector'].get('bank_path')!=bank:return False
    profile=selected_profile(directory,segment)
    clearance=profile.get('role_clearance')if profile else None
    saved=data.get('skin_role_evidence')
    if clearance is None:return saved is None
    from piu_timeline.play.skins.clearance import FORMAT as CLEARANCE_FORMAT
    contract=(saved or{}).get('contract',{})
    return (contract.get('profile')==clearance and contract.get('format')==CLEARANCE_FORMAT
            and contract.get('skin')==data['skin_detector']['contract'])


def refresh(data, output, path):
    """A detector change rescans RGB, never reuses old contour detections as input."""
    bank = load_bank(path)
    before = Path(data['media']['path']).stat()
    if (before.st_size, before.st_mtime_ns) != (data['media']['size_bytes'], data['media']['mtime_ns']):
        raise ValueError('Skin replay source no longer matches its acquisition identity')
    trace = output / 'frames.jsonl'
    backup = output / 'frames.outline.jsonl'
    if not data.get('skin_detector')and not backup.exists():
        from piu_timeline.play.observations.cache import is_outline_trace
        if not is_outline_trace(trace):raise ValueError('Unlabelled image observations cannot become an outline backup')
        shutil.copy2(trace, backup)
    target = output / 'frames.skin-build.jsonl'
    from piu_timeline.play.skins.reuse import reusable_groups, group, merge_observations
    reused=reusable_groups(data,bank)
    selected={**bank,'templates':[t for t in bank['templates']if group(t)not in reused]}
    if reused:print('Reusing unchanged skin image groups: '+', '.join(sorted(reused)),flush=True)
    decoded=None
    if selected['templates']:
        source=decode_frames(data['media'], data['start_seconds'], data['end_seconds'],
                             data['game_roi'], data['analysis_width'])
        decoded=classified_frames(source,selected,data['layout'],data['analysis_width'],data['analysis_height'])
    detector=SkinDetector(bank,data['layout'],data['analysis_width'],data['analysis_height'])
    at_receptor=BodyAtReceptor(detector)
    from piu_timeline.play.skins.subfeatures import account
    count,last = 0,None
    lifetime=closing(decoded)if decoded is not None else nullcontext()
    with trace.open() as source, target.open('w') as stream, lifetime:
        paired=zip_longest(source,decoded)if decoded is not None else((line,None)for line in source)
        for line, frame in paired:
            if line is None or decoded is not None and frame is None:
                raise ValueError('Skin image replay differs from native frame count')
            native = json.loads(line)
            stamp=(native['source_pts_seconds'],native['playback_seconds'])
            if not all(math.isfinite(t)for t in stamp)or last is not None and any(a<=b for a,b in zip(stamp,last)):
                raise ValueError('Skin replay source timestamps must be finite and increasing')
            last=stamp
            if reused and 'skin_observations'not in native:
                raise ValueError('Reusable skin groups have no native image observations')
            if decoded is None:
                pts,time=native['source_pts_seconds'],native['playback_seconds'];observations=[]
            else:pts, time, _, observations = frame
            if abs(pts - native['source_pts_seconds']) > 1e-6 or abs(time - native['playback_seconds']) > 1e-6:
                raise ValueError('Skin image replay differs from original PTS')
            observations=merge_observations(native,observations,reused)
            observations=account(observations,detector.by_sampling,data['analysis_width'],data['analysis_height'])
            native.update(notes=[o for o in observations if o['role'] != 'hold_body'],
                          skin_observations=observations,
                          possible_hold_or_dense_stack=at_receptor(observations))
            stream.write(json.dumps(native) + '\n')
            count += 1
            if count % 600 == 0:
                phase='Skin observation reinterpretation'if decoded is None else'Skin image replay'
                print(f'  {phase}: {time-data["start_seconds"]:.1f}s', flush=True)
    after = Path(data['media']['path']).stat()
    if count != data['frame_count'] or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Source identity or native frame count changed during skin replay')
    target.replace(trace)
    shutil.copy2(trace, output / 'frames.base.jsonl')
    return detector_metadata(path, bank)
