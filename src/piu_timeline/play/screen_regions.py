"""Named game-image regions; only documented foreground HUD can hide heads."""


def note_occluders(layout):
    """Return existing HUD footprints in normalized full-game coordinates."""
    if 'combo_roi' not in layout:
        return []
    from piu_timeline.play.judgments import judgment_region
    x,y,w,h = layout['combo_roi']
    return [{'id':'judgment_word','rect':judgment_region(layout)},
            {'id':'combo_label_and_digits','rect':[x,max(0,y-.06),w,h+min(.06,y)]}]


def overlapping_occluders(layout, lane, center_y, width, height, spacing):
    """A cap footprint must actually intersect a named HUD rectangle."""
    x = layout['lanes'][lane]['x']*width
    half = .5*spacing
    return [region['id'] for region in note_occluders(layout)
            if (region['rect'][0]*width < x+half
                and (region['rect'][0]+region['rect'][2])*width > x-half
                and region['rect'][1]*height < center_y+half
                and (region['rect'][1]+region['rect'][3])*height > center_y-half)]
