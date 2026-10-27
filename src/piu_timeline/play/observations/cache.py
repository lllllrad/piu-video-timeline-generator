"""Select compatible immutable native-observation backups."""
import json
import re

from piu_timeline.storage import read_analysis_header as cache_header

NATIVE_FRAME_FORMAT = {'schema':1,'notes':'normalized_lane_centers','time':'source_pts_and_playback'}


def observation_settings_match(cached, document, segment, start, end, options):
    chart=segment.get('chart') or ''
    lanes=10 if re.match(r'^(?:HD|D)\d',chart) else 5 if re.match(r'^(?:S\d|VERY HARD )',chart) else None
    return (cached.get('media')==document.get('media') and cached.get('start_seconds')==start
            and cached.get('end_seconds')==end and cached.get('game_roi')==document.get('game_roi')
            and cached.get('analysis_width')==options.get('width',650)
            and cached.get('player')==options.get('player')
            and cached.get('participant_slots',[])==sorted(segment.get('players',{}))
            and (lanes is None or len(cached.get('layout',{}).get('lanes',[]))==lanes)
            and (options.get('layout') is None or cached.get('layout')==options['layout']))


def find_saved_observations(root, final, document, segment, start, end, options):
    # Backups are immutable snapshots, so another segment can reuse them safely
    # while the numbered presentation directories are being updated.
    paths=[p for p in root.glob('segment-*.previous-*/analysis.json') if p.parent!=final]
    for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:
            cached=cache_header(path)
            if (observation_settings_match(cached,document,segment,start,end,options)
                    and (path.parent/'frames.jsonl').is_file()
                    and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT):
                cached=json.loads(path.read_text())
                if (observation_settings_match(cached,document,segment,start,end,options)
                        and cached.get('native_frame_format',NATIVE_FRAME_FORMAT)==NATIVE_FRAME_FORMAT
                        and all(key in cached for key in ('layout','analysis_height','frame_count'))):
                    return cached,path.parent
        except (OSError,ValueError):
            continue
    return None


