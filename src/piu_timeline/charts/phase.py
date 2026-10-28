"""Use the TypeScript bounded song-phase translation for UCS export."""
from dataclasses import asdict
from piu_timeline.derived import call


def transcription_alignment(template,data,alignment):
    try:
        return tuple(call('chartPhase.transcriptionAlignment',asdict(template),
                          {'beat_timing':data.get('beat_timing')},alignment))
    except ValueError as error:
        if 'not JSON compliant'in str(error):
            raise ValueError('Invalid bounded common song phase for UCS transcription')from error
        raise
