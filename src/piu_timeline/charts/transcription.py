"""Compatibility adapter for exact TypeScript per-measure UCS transcription."""
from dataclasses import asdict
from fractions import Fraction
from piu_timeline.derived import CONTRACTS, call
from piu_timeline.charts.ucs import document
FORMAT=CONTRACTS['transcription']
EPSILON=1e-8


def measures(source):
    result=call('transcription.measures',asdict(source))
    for span in result:
        for key in ('phase','beats','start','end','beat_duration'):span[key]=Fraction(span[key])
        span['directives']=[tuple(d)for d in span['directives']]
    return result


def choices(span,split,lower,upper,following):
    saved={k:str(v)if isinstance(v,Fraction)else v for k,v in span.items()}
    return call('transcription.choicesFromJSON',saved,split,lower,upper,following)


def transcribe(source,endpoints):
    keys=list(endpoints)
    saved={str(i):endpoints[k]for i,k in enumerate(keys)}
    result,grid,accepted,failures,proof=call('transcription.transcribe',asdict(source),saved)
    return (document(result),[(si,ri,Fraction(t))for si,ri,t in grid],
            {keys[int(i)]:r for i,r in accepted.items()},
            {keys[int(i)]:r for i,r in failures.items()},proof)
