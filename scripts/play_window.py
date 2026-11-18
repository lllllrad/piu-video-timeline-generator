"""Review all play stages for a bounded source-time window."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
from uuid import uuid4

from piu_timeline import ROOT
from piu_timeline.play.analysis import TIMING_FORMAT, analyze_play, finish_play
from piu_timeline.storage import read_analysis_header
from piu_timeline.workflow import LOCAL_DATA, source_id


def playback_seconds(value):
    """Parse seconds, MM:SS.sss or HH:MM:SS.sss."""
    if not re.fullmatch(r'(?:\d+:){0,2}\d+(?:\.\d+)?', value):
        raise argparse.ArgumentTypeError('Use seconds, MM:SS.sss or HH:MM:SS.sss')
    parts = [float(part) for part in value.split(':')]
    seconds = sum(part * 60**power for power, part in enumerate(reversed(parts)))
    if not math.isfinite(seconds) or (len(parts) > 1 and any(part >= 60 for part in parts[1:])):
        raise argparse.ArgumentTypeError('Use finite playback time with minute/second fields below 60')
    return seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('segment', type=int)
    parser.add_argument('start', type=playback_seconds)
    parser.add_argument('end', type=playback_seconds, help='Exclusive playback end')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--observations-only', action='store_true')
    mode.add_argument('--reuse-native', type=Path, metavar='RUN_DIRECTORY')
    args = parser.parse_args()
    if args.segment < 1 or args.start >= args.end:
        parser.error('Provide a positive segment number and an increasing playback interval')

    try:
        source = source_id(args.source)
        directory = LOCAL_DATA / source
        metadata = json.loads((directory / 'analysis/analysis.json').read_text())
        if args.segment > len(metadata['segments']):
            raise ValueError('Segment is missing from source metadata')
        segment = metadata['segments'][args.segment - 1]
        if not segment['start_seconds'] <= args.start < args.end <= segment['end_seconds']:
            raise ValueError('Requested window must lie inside the gameplay segment')

        play = directory / 'play' / f'segment-{args.segment:03}'
        saved = read_analysis_header(play / 'analysis.json')
        if saved['media'] != metadata['media'] or saved['game_roi'] != metadata['game_roi']:
            raise ValueError('Saved play geometry belongs to a different source or game ROI')
        name = f'play-window-{source}-{args.segment:03}-{uuid4().hex[:8]}'
        final = ROOT / '.local/reports' / name / 'play' / f'segment-{args.segment:03}'
        output = (ROOT / '.local/runs' / name if args.observations_only else
                  final.with_name(final.name + '.build-' + uuid4().hex[:8]))
        print(f'Play window [{args.start:.3f}, {args.end:.3f}) → {output}', flush=True)
        if args.reuse_native:
            donor = args.reuse_native.resolve()
            result = json.loads((donor/'analysis.json').read_text())
            if (not (donor/'frames.jsonl').is_file()
                    or any(result[key] != saved[key] for key in ('media', 'game_roi', 'layout', 'analysis_width'))
                    or result['skin_detector']['bank_path'] != saved['skin_detector']['bank_path']
                    or result['segment_number'] != args.segment
                    or (result['start_seconds'], result['end_seconds']) != (args.start, args.end)):
                raise ValueError('Native run does not match the source, geometry, skin or interval')
            native = {'analysis.json', 'frames.jsonl', 'frames.base.jsonl', 'frames.combo-baseline.jsonl',
                      'comparison-evidence', 'counter-events.json', 'counter-pixels.npz',
                      'evidence', 'layout.json', 'preview.png'}
            shutil.copytree(donor, output, ignore=lambda path, names: set(names)-native if Path(path)==donor else [])
            from piu_timeline.storage import relocate_evidence
            relocate_evidence(output, output, source=donor)
        else:
            result = analyze_play(
                metadata, segment, output, player=saved.get('player'), layout=saved['layout'],
                start=args.start, duration=args.end - args.start, width=saved['analysis_width'],
                note_skin=saved['skin_detector']['bank_path'],
                digit_templates=play / 'evidence/digit-templates.npz',
            )
        result['segment_number'] = args.segment
        if args.observations_only:
            (output / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(f"{result['frame_count']} native frames → {output / 'frames.jsonl'}")
            return

        # Whole-song score statistics do not describe this window.
        result['result_reference'] = None
        from piu_timeline.play.skins.bank import load_bank
        from piu_timeline.play.stages import execute
        from piu_timeline.play.tracking import replay
        bank = load_bank(result['skin_detector']['bank_path'])
        tracked = execute(output, 'tracking', lambda: replay(result, output, bank), ('tracking.json',))
        report = finish_play({**result, **tracked, 'timing_format': TIMING_FORMAT}, output, final,
                             args.segment, result['display_delay_correction_ms'], result['media'],
                             review_window=True)
        print(report)
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
