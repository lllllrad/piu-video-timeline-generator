"""Python values for UCS documents; exact timing algorithms live in TypeScript."""
from dataclasses import asdict, dataclass
from fractions import Fraction
from piu_timeline.derived import CONTRACTS,call

NATURAL_SPLITS=tuple(CONTRACTS['natural_splits'])


@dataclass
class Section:
    directives:list
    rows:list


@dataclass
class Document:
    header:list
    sections:list

    @property
    def mode(self):return dict(self.header)['Mode']

    @property
    def lanes(self):return {'Single':5,'Double':10}[self.mode]

    def grid(self):
        for si,ri,time in call('ucs.grid',asdict(self)):yield si,ri,Fraction(time)

    def expanded(self,lanes,subdivisions=1):
        return document(call('ucs.expanded',asdict(self),lanes,subdivisions))

    def text(self):return call('ucs.text',asdict(self))


def document(value):
    return Document([tuple(d)for d in value['header']],
                    [Section([tuple(d)for d in s['directives']],s['rows'])for s in value['sections']])


def parse(text):return document(call('ucs.parse',text))


def constant_tempo(template,catalogue_bpm):
    return call('ucs.constantTempo',asdict(template),catalogue_bpm)
