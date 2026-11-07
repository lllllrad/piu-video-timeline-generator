"""Independent two-dimensional checks across declared connector artwork."""
import numpy as np

FORMAT={'schema':1,'method':'masked_spatial_cells','rows':3,'columns':3}


def cells(region):
    """Partition supported pixels, including disconnected shoulders and corners.

    Empty cells carry no evidence. Every nonempty cell keeps the original RGB
    tolerance; a good center cannot average away a failed edge or neck.
    """
    mask=region['mask'];height,width=mask.shape
    xs=np.unique(np.linspace(0,width,FORMAT['columns']+1,dtype=int))
    ys=np.unique(np.linspace(0,height,FORMAT['rows']+1,dtype=int))
    left,top,_,_=region['box']
    for a,c in zip(xs,xs[1:]):
        for b,d in zip(ys,ys[1:]):
            support=mask[b:d,a:c]
            if not support.any():continue
            yield {**region,'box':[left+int(a),top+int(b),left+int(c),top+int(d)],'mask':support.copy()}


VISIBLE_FORMAT={'schema':1,'method':'measured_foreground_exclusion_per_cell',
                'minimum_visible_cell_fraction':.5}


def visible_region(image,template,region,left,top,hidden,independent=None):
    """Every independently supported cell must remain at least half visible.

    Only known foreground can remove pixels. Required cap features and negative
    clearance checks do not use this partial positive-connector comparison.
    """
    a,b,c,d=region['box'];available=region['mask'].astype(bool).copy()
    if independent is not None:available&=independent[b:d,a:c]
    visible=available&~hidden[top+b:top+d,left+a:left+c]
    errors=[]
    for part in region.get('_cells')or[region]:
        x,y,z,v=part['box'];support=available[y-b:v-b,x-a:z-a]
        if not support.any():continue
        selected=visible[y-b:v-b,x-a:z-a]
        if selected.sum()<VISIBLE_FORMAT['minimum_visible_cell_fraction']*support.sum():return None
        delta=image[top+y:top+v,left+x:left+z]-template['rgb'][y:v,x:z]
        errors.append(float(np.square(delta[selected]).mean()))
    if not errors:return None
    return max(errors),visible
