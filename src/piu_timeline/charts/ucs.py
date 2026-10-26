"""Editable UCS documents with exact section timing and explicit hold bodies."""
from dataclasses import dataclass
from fractions import Fraction
from math import lcm
import re


@dataclass
class Section:
    directives: list
    rows: list


@dataclass
class Document:
    header: list
    sections: list

    @property
    def mode(self):
        return dict(self.header)['Mode']

    @property
    def lanes(self):
        return {'Single': 5, 'Double': 10}[self.mode]

    def grid(self):
        """Yield (section, row, seconds); Delay is milliseconds per section."""
        time = Fraction(0)
        settings = {}
        for si, section in enumerate(self.sections):
            directives = dict(section.directives)
            settings.update(directives)
            time += Fraction(directives.get('Delay', '0')) / 1000
            step = 60 / (Fraction(settings['BPM']) * int(settings['Split']))
            for ri in range(len(section.rows)):
                yield si, ri, time
                time += step

    def expanded(self, lanes, subdivisions=48):
        """Preserve section durations when inserting finer empty timing rows."""
        if lanes not in (5, 10) or not 1 <= subdivisions <= 192:
            raise ValueError('Unsupported lane count or subdivision')
        header = [(key, ('Single' if lanes == 5 else 'Double') if key == 'Mode' else value)
                  for key, value in self.header]
        sections, old_split = [], None
        for section in self.sections:
            old_split = int(dict(section.directives).get('Split', old_split))
            split = lcm(old_split, subdivisions)
            if split > 1536:
                raise ValueError('UCS subdivision expansion is too large')
            directives = [(key, str(split) if key == 'Split' else value) for key, value in section.directives]
            if not any(key == 'Split' for key, _ in directives):
                directives.append(('Split', str(split)))
            # Official templates must be empty; never erase a human's notes.
            if any(set(row) != {'.'} for row in section.rows):
                raise ValueError('Expected an empty timing template')
            sections.append(Section(directives, ['.' * lanes] * (len(section.rows) * (split // old_split))))
        return Document(header, sections)

    def text(self):
        lines = [f':{key}={value}' for key, value in self.header]
        for section in self.sections:
            lines.extend(f':{key}={value}' for key, value in section.directives)
            lines.extend(section.rows)
        return '\n'.join(lines) + '\n'


def parse(text):
    header, sections, directives, rows = [], [], [], []
    settings = {}
    for raw in text.lstrip('\ufeff').splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(':'):
            if '=' not in line:
                raise ValueError('Malformed UCS directive')
            key, value = line[1:].split('=', 1)
            if key in ('Format', 'Mode'):
                if rows or sections or directives or any(k == key for k, _ in header):
                    raise ValueError('UCS header must precede timing sections')
                header.append((key, value))
                continue
            if key not in ('BPM', 'Delay', 'Beat', 'Split'):
                raise ValueError(f'Unsupported UCS directive: {key}')
            if rows:
                sections.append(Section(directives, rows))
                directives, rows = [], []
            if any(k == key for k, _ in directives):
                raise ValueError(f'Duplicate UCS directive: {key}')
            try:
                number = Fraction(value)
                if key != 'Delay' and number <= 0 or key in ('Beat', 'Split') and number.denominator != 1:
                    raise ValueError('Invalid UCS timing value')
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError(f'Invalid UCS {key}: {value}') from error
            directives.append((key, value))
            settings[key] = value
        else:
            if not {'BPM', 'Beat', 'Split'} <= settings.keys():
                raise ValueError('UCS rows require BPM, Beat and Split')
            mode = dict(header).get('Mode')
            if mode not in ('Single', 'Double') or len(line) != (5 if mode == 'Single' else 10) or set(line) - set('.XMHW'):
                raise ValueError('Invalid UCS note row')
            rows.append(line)
    if rows:
        sections.append(Section(directives, rows))
    elif directives:
        raise ValueError('UCS section has no timing rows')
    if dict(header).get('Format') != '1' or not sections:
        raise ValueError('Expected a nonempty Format=1 UCS document')
    return Document(header, sections)


def constant_tempo(template, catalogue_bpm):
    """Only independent catalogue/template agreement permits tail extension."""
    return (isinstance(catalogue_bpm,str) and re.fullmatch(r'\d+(?:\.\d+)?',catalogue_bpm) is not None
            and Fraction(catalogue_bpm)>0
            and {Fraction(value) for section in template.sections for key,value in section.directives if key=='BPM'}
                =={Fraction(catalogue_bpm)})
