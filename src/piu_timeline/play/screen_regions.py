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
    return occluders_at_bounds(layout,[x-half,center_y-half,x+half,center_y+half],width,height)


def occluders_at_bounds(layout,bounds,width,height):
    """Intersect an actual pixel rectangle with the documented HUD footprints."""
    return [region['id']for region in note_occluders(layout)
            if bounds[0]<(region['rect'][0]+region['rect'][2])*width and region['rect'][0]*width<bounds[2]
            and bounds[1]<(region['rect'][1]+region['rect'][3])*height and region['rect'][1]*height<bounds[3]]


def visible_cap_bounds(data,lane,detected_y,box,patch_shape,spacing,margin=0):
    """Check the measured cap footprint, including any required clear margins."""
    width,height=data['analysis_width'],data['analysis_height'];layout=data['layout']
    left=round(layout['lanes'][lane]['x']*width)-(patch_shape[1]-1)//2
    top=round(detected_y)-(patch_shape[0]-1)//2
    x,y,w,h=box
    bounds=[left+x,top+y-margin,left+x+w,top+y+h+margin]
    if (bounds[0]<0 or bounds[2]>width
            or bounds[1]<layout['receptor_y']*height+.3*spacing
            or bounds[3]>layout.get('note_y_max',.95)*height):return None
    if occluders_at_bounds(layout,bounds,width,height):return None
    return bounds
