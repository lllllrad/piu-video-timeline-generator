"""TypeScript audit of measured native speed, stops and reversals."""
from piu_timeline.derived import call
from piu_timeline.play.continuity import inputs
from piu_timeline.play.screen_regions import note_occluders


def motion_warnings(data,frames):
    return call('visibility.motionWarnings',inputs(data),frames,note_occluders(data.get('layout',{})))
