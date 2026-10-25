"""Declared Phoenix receptor positions relative to the full game image."""
import re


RECEPTOR_Y = .142
SINGLE_X = {
    'p1': (.195, .254, .313, .372, .431),
    'p2': (.570, .629, .688, .747, .806),
}
DOUBLE_X = (.235, .29423, .35346, .41269, .47135,
            .52962, .58885, .64808, .7075, .76654)
COLORS = ('blue', 'red', 'yellow', 'red', 'blue')
NAMES = ('DL', 'UL', 'C', 'UR', 'DR')


def fixed_layout(segment, player=None):
    """Select a declared layout, without claiming image-detected receptors.

    The game ROI must be the full, unmirrored game image. Single requires a
    known player side; missing mode/side uses the visual/manual fallback.
    """
    chart = segment.get('chart') or ''
    if re.fullmatch(r'D\d{1,2}', chart):
        xs, profile = DOUBLE_X, 'double'
    elif re.fullmatch(r'S\d{1,2}|VERY HARD \d{1,2}', chart):
        players = segment.get('players', {})
        side = player or (next(iter(players)) if len(players) == 1 else None)
        if side not in SINGLE_X:
            return None
        xs, profile = SINGLE_X[side], 'single_'+side
    else:
        return None
    middle = sum(xs)/len(xs)
    return {'method': 'fixed_phoenix_game_layout', 'profile': profile, 'profile_revision': 1,
            'receptor_y': RECEPTOR_Y, 'note_y_max': .95,
            'combo_roi': [middle-.07, .52, .14, .075],
            'lanes': [{'x': x, 'color': COLORS[index % 5],
                       'name': f'{index//5+1}:{NAMES[index % 5]}'} for index, x in enumerate(xs)]}
