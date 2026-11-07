"""Ungrouped detector observations from original source frames; no timing or popup input."""
from contextlib import closing, nullcontext
import gzip
import json
from pathlib import Path
import shutil
from uuid import uuid4

from piu_timeline.play.observations.artifacts import save_input
from piu_timeline.play.frames import decode_frames
from piu_timeline.play.observations.bundle import read_manifest, digest, source_current

FORMAT={'schema':1,'revision':1,'measurement':'ungrouped_localized_detections'}


def detect_notes(directory,bank=None,*,jobs=None,detector=None):
    if (bank is None)==(detector is None):raise ValueError('Choose exactly one note detector')
    from piu_timeline.play.skins.detector import FORMAT as IMAGE_FORMAT
    pixels=read_manifest(directory)
    if pixels is None:raise ValueError('Acquire the independent timeline before detecting notes')
    bound=pixels['contract']['source']
    detector_contract=detector.contract if detector is not None else {'method':'skin_image','bank':bank['contract'],'format':IMAGE_FORMAT}
    binding={'format':FORMAT,'pixels':digest(directory/'manifest.json'),'detector':detector_contract}
    target=directory/'notes';path=target/'manifest.json'
    if path.is_file():
        saved=json.loads(path.read_text())
        if saved.get('contract')==binding:
            for chunk in saved['chunks']:
                for name,identity in chunk['files'].items():
                    if digest(target/name)!=identity:raise ValueError('Corrupt note observation chunk')
            return saved
    pending=directory/('.notes.'+uuid4().hex+'.build');pending.mkdir()
    previous=directory/'.notes.previous'
    try:
        decoded=decode_frames(bound['media'],bound['start_seconds'],bound['end_seconds'],bound['game_roi'],bound['width'])
        if detector is not None:
            frames=((pts,time,rgb,detector.candidates(rgb))for pts,time,rgb in decoded)
        else:
            from piu_timeline.play.skins.pipeline import classified_frames
            frames=classified_frames(decoded,bank,bound['layout'],bound['width'],bound['height'],jobs=jobs,retain_candidates=True)
        chunks=[];rows=[];index=0;ci=0
        lifetime=closing(decoded)if hasattr(decoded,'close')else nullcontext(decoded)
        with lifetime,closing(frames):
            for pts,time,rgb,candidates in frames:
                if ci>=len(pixels['chunks']):raise ValueError('Extra source frame during note detection')
                if not rows:
                    native=pixels['chunks'][ci]
                    names=[name for name in native['files']if name.endswith('.frames.jsonl.gz')]
                    if len(names)!=1:raise ValueError('Missing captured frame timeline')
                    file=directory/names[0]
                    if digest(file)!=native['files'][names[0]]:raise ValueError('Corrupt captured frame timeline')
                    timeline=[json.loads(line)for line in gzip.decompress(file.read_bytes()).splitlines()]
                    if len(timeline)!=native['frames']:raise ValueError('Incomplete captured frame timeline')
                expected=timeline[len(rows)]
                if (expected['frame']!=index or abs(expected['source_pts_seconds']-pts)>1e-6
                        or abs(expected['playback_seconds']-time)>1e-6):
                    raise ValueError('Source frame differs from captured original PTS')
                rows.append({'frame':index,'source_pts_seconds':pts,'playback_seconds':time,
                             'note_candidates':[{**c,'candidate':i}for i,c in enumerate(candidates)]})
                index+=1
                if len(rows)==pixels['chunks'][ci]['frames']:
                    name=f'{ci:05}.notes.jsonl.gz';file=pending/name
                    file.write_bytes(gzip.compress(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n'for r in rows).encode(),compresslevel=1,mtime=0))
                    chunks.append({'first_frame':index-len(rows),'frames':len(rows),'files':{name:digest(file)}})
                    rows.clear();ci+=1
                    save_input(pending/'progress.json',{'frames':index,'total_frames':pixels['frame_count']})
        if rows or index!=pixels['frame_count'] or len(chunks)!=len(pixels['chunks']):raise ValueError('Note observations differ from original pixel timeline')
        source_current(bound)
        result={'schema':1,'capture_state':'complete','recognition_state':'candidate_observations',
                'contract':binding,'frame_count':index,'chunks':chunks}
        save_input(pending/'manifest.json',result)
        if previous.exists():shutil.rmtree(previous)
        if target.exists():target.rename(previous)
        try:pending.rename(target)
        except BaseException:
            if previous.exists():previous.rename(target)
            raise
        if previous.exists():shutil.rmtree(previous)
        return result
    finally:
        shutil.rmtree(pending,ignore_errors=True)


def retained_frames(data,bank):
    """Adapt compatible independent observations for existing tracking consumers."""
    from piu_timeline.play.observations.bundle import for_play
    directory=for_play(data)
    if directory is None:return None
    path=directory/'notes/manifest.json'
    if not path.is_file():return None
    from piu_timeline.play.skins.detector import FORMAT as IMAGE_FORMAT
    expected={'format':FORMAT,'pixels':digest(directory/'manifest.json'),
              'detector':{'method':'skin_image','bank':bank['contract'],'format':IMAGE_FORMAT}}
    saved=json.loads(path.read_text())
    if saved.get('contract')!=expected:return None
    if saved['frame_count']!=data.get('frame_count'):return None
    def rows():
        count=0
        for chunk in saved['chunks']:
            if chunk['first_frame']!=count:raise ValueError('Independent note timeline has a gap')
            for name,identity in chunk['files'].items():
                file=directory/'notes'/name
                if Path(name).is_absolute()or '..'in Path(name).parts or digest(file)!=identity:
                    raise ValueError('Corrupt independent note observations')
                values=gzip.decompress(file.read_bytes()).splitlines()
                if len(values)!=chunk['frames']:raise ValueError('Independent note frame count differs')
                for line in values:
                    frame=json.loads(line)
                    if frame['frame']!=count:raise ValueError('Independent note frame identity differs')
                    count+=1
                    yield frame['source_pts_seconds'],frame['playback_seconds'],frame['note_candidates']
        if count!=saved['frame_count']:raise ValueError('Independent note observations are incomplete')
    return rows()
