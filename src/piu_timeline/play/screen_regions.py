"""Named game-image regions; only documented foreground HUD can hide heads."""

FORMAT={'schema':1,'revision':2,'method':'foreground_hud_footprints',
        'judgment_width_combo_ratio':2.,'judgment_top_offset':-.155,'judgment_height':.11,
        'combo_label_width_ratio':1.4,'combo_label_top_offset':-.045}


def _rect(center,top,width,height):
    left,right=max(0,center-width/2),min(1,center+width/2)
    bottom=min(1,top+height);top=max(0,top)
    return [left,top,right-left,max(0,bottom-top)]


def note_occluders(layout):
    """Foreground footprints, independent of the larger OCR search window."""
    if 'combo_roi' not in layout:
        return []
    x,y,w,h = layout['combo_roi']
    center=x+w/2
    word=layout.get('judgment_roi',_rect(center,y+FORMAT['judgment_top_offset'],
                                      w*FORMAT['judgment_width_combo_ratio'],FORMAT['judgment_height']))
    return [{'id':'judgment_word','rect':word},
            {'id':'combo_label','rect':_rect(center,y+FORMAT['combo_label_top_offset'],
                                           w*FORMAT['combo_label_width_ratio'],-FORMAT['combo_label_top_offset'])},
            {'id':'combo_digits','rect':[x,y,w,h]}]


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
    """Bound an independently matched cap; HUD overlap does not erase pixels.

    This validates positive geometry only. Callers proving absence of a body
    must separately check whether foreground HUD could conceal that body.
    """
    width,height=data['analysis_width'],data['analysis_height'];layout=data['layout']
    left=round(layout['lanes'][lane]['x']*width)-(patch_shape[1]-1)//2
    top=round(detected_y)-(patch_shape[0]-1)//2
    x,y,w,h=box
    bounds=[left+x,top+y-margin,left+x+w,top+y+h+margin]
    if (bounds[0]<0 or bounds[2]>width
            or bounds[1]<layout['receptor_y']*height+.3*spacing
            or bounds[3]>layout.get('note_y_max',.95)*height):return None
    return bounds
