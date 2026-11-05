"""Measured cap pixels, distinct from hidden reference artwork."""
import numpy as np


def cap_support(template,pattern):
    support=template['cap_support']
    if 'visible_cap_runs'not in pattern:return support
    visible=np.zeros_like(support)
    for y,a,b in pattern['visible_cap_runs']:visible[y,a:b]=True
    return support&visible
