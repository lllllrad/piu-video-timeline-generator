"""Validate separate-repository chart facts using exact TypeScript UCS timing."""
from dataclasses import asdict
from piu_timeline.derived import call


def validate(document,assertions):
    call('chartAssertions.validate',asdict(document),assertions)
