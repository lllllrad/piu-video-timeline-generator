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
