"""Locate image patterns directly, without generating contour candidates first."""
import cv2
import numpy as np
import math

from piu_timeline.play.screen_regions import note_occluders
from piu_timeline.play.skins.sampling import models,key,reference_scale,FORMAT as SAMPLING_FORMAT
from piu_timeline.play.skins.subfeatures import account
from piu_timeline.play.skins.canvas import comparison_canvas
from piu_timeline.play.skins.matching import RegionSearch,prepare_regions
from piu_timeline.play.skins.spatial import FORMAT as SPATIAL_FORMAT
from piu_timeline.play.skins.overlap import FORMAT as OVERLAP_FORMAT,recover
from piu_timeline.play.skins.shared_roles import FORMAT as SHARED_ROLE_FORMAT,candidates as shared_roles
from piu_timeline.play.skins.classification import FORMAT as CLASSIFICATION_FORMAT,QUALIFIED,identify

FORMAT = {'schema': 1, 'revision': 10,'classification':CLASSIFICATION_FORMAT, 'shared_roles':SHARED_ROLE_FORMAT, 'method': 'lane_masked_rgb_regions','spatial_support':SPATIAL_FORMAT,'overlap':OVERLAP_FORMAT,'sampling':SAMPLING_FORMAT,
          'scale_basis':'declared_uniform_game_frame_or_lane_spacing',
          'horizontal_search_spacing': .12, 'same_anchor_spacing': .25, 'vertical_limit': 'anchor',
          'body_candidates': {'schema':1,'selection':'qualified_rows_horizontal_minima'}}


def occluded_support(layout, support, left, top, width, height):
    """Transparent padding and pixels outside compared regions carry no proof."""
    for region in note_occluders(layout):
        x,y,w,h=region['rect']
        a=max(0,math.floor(x*width-left));b=min(support.shape[1],math.ceil((x+w)*width-left))
        c=max(0,math.floor(y*height-top));d=min(support.shape[0],math.ceil((y+h)*height-top))
        if a<b and c<d and support[c:d,a:b].any():return True
    return False


class SkinDetector:
    def __init__(self, bank, layout, width, height):
        self.bank, self.layout, self.width, self.height = bank, layout, width, height
        self.spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
        self.same_anchor_pixels=FORMAT['same_anchor_spacing']*self.spacing
        self.templates = []
        scale = reference_scale(bank,layout,width,height)
        for original in bank['templates']:
            variants=[comparison_canvas(model)for model in models(original,scale)]
            if not variants:raise ValueError('Skin image region vanishes at the analysis scale')
            self.templates.extend(variants)
        self.by_sampling={key(t):t for t in self.templates}
        for template in self.templates:prepare_regions(template)
        self.shared_contexts={f['id']:[t for t in self.templates if t['id']in f['role_templates']]
                              for f in bank.get('shared_cap_families',[])}

    def search_bounds(self,column,template):
        h,w=template['mask'].shape;ax,ay=template['anchor']
        radius=max(1,round(FORMAT['horizontal_search_spacing']*self.spacing))
        left=max(0,round(column['x']*self.width-ax)-radius)
        right=min(self.width,round(column['x']*self.width-ax)+w+radius)
        top=max(0,int(self.layout['receptor_y']*self.height+.55*self.spacing-ay))
        return [left,top,right,self.height]if right-left>=w and self.height-top>=h else None

    def detect(self, rgb):
        return self.resolve(self.candidates(rgb))

    def candidates(self, rgb):
        """Measure every localized match before grouping or object interpretation.

        Nearby caps, incompatible roles and body matches inside caps stay separate.
        Only image-region comparisons and local extrema belong to acquisition.
        """
        if rgb.shape != (self.height, self.width, 3):
            raise ValueError('Skin detector image differs from its geometry')
        image = rgb.astype('float32') / 255
        searcher=RegionSearch(image)
        candidates = []
        for lane, column in enumerate(self.layout['lanes']):
            for template in self.templates:
                if template['lane_kind'] != lane % 5:
                    continue
                h, w = template['mask'].shape
                ax, ay = template['anchor']
                search=self.search_bounds(column,template)
                if search is None:continue
                left,top,right,bottom=search
                evaluated=searcher.evaluate(template,search)
                if evaluated is None:continue
                scores,proposal_scores,errors=evaluated
                allowed = np.isfinite(proposal_scores) & (proposal_scores <= 1)
                # Caps need a localized origin; body tiles measure supported rows.
                kernel=(1,3)if template['role']=='hold_body'else(3,3)
                minima = cv2.erode(proposal_scores.astype('float32'), np.ones(kernel, dtype='uint8'))
                rows, cols = np.nonzero(allowed & (proposal_scores <= minima + 1e-7))
                for row, col in zip(rows, cols, strict=True):
                    x, y = left + col + ax, top + row + ay
                    if y > self.layout.get('note_y_max',.95)*self.height:
                        continue
                    bounds = [left + int(col), top + int(row), left + int(col) + w, top + int(row) + h]
                    hidden=occluded_support(self.layout,template['support'],bounds[0],bounds[1],self.width,self.height)
                    cap_only='cap'in errors and (not np.isfinite(scores[row,col]) or scores[row,col]>1
                                or template['role']=='tap' and not template['tap_clearance'])
                    candidates.append({'lane': lane, 'x': x / self.width, 'y': y / self.height,
                                       'role': 'unknown'if cap_only else template['role'], 'template': template['id'],
                                       'template_role':template['role'], 'hud_region_overlap':hidden,
                                       **({k:template[k]for k in ('sampling_phase_pixels','reference_scale_y','sampling_kernel','sampling_origin_pixels')if k in template}),
                                       'classification_status':'cap_only'if cap_only else'full_pattern',
                                       **({'reason':'skin_tap_clearance_unresolved'if template['role']=='tap'
                                           else'skin_image_connection_unresolved'}if cap_only else{}),
                                       'quality': float(1 - (proposal_scores[row,col]if cap_only else scores[row, col])),
                                       'region_errors': {name: float(values[row,col])if np.isfinite(values[row,col])else None for name,values in errors.items()},
                                       **({'unavailable_regions':[name for name,values in errors.items()if not np.isfinite(values[row,col])]}
                                          if any(not np.isfinite(values[row,col])for values in errors.values())else{}),
                                       'bounds_pixels': bounds, 'method': 'skin_image', 'skin': self.bank['skin']})
        candidates.extend(recover(self,image,candidates))
        candidates.extend(shared_roles(self,image,candidates))
        return candidates

    def resolve(self, candidates):
        candidates=[identify(self.by_sampling[key(c)],c)for c in candidates]
        retained = []
        for candidate in sorted(candidates, key=lambda c: c['quality'], reverse=True):
            peers = [r for r in retained if r['lane'] == candidate['lane']
                     and abs(r['y'] - candidate['y']) * self.height < self.same_anchor_pixels
                     and (r['role'] == 'hold_body') == (candidate['role'] == 'hold_body')]
            if not peers:
                retained.append({**candidate, 'alternatives': []})
                continue
            current = peers[0]
            fields=('role','template_role','classification_status','template','quality','region_errors',
                    'x','y','bounds_pixels','shared_role','role_evidence','visible_cap_runs','visible_connection_runs','occlusion_evidence','sampling_phase_pixels','reference_scale_y','sampling_kernel','sampling_origin_pixels','unavailable_regions')
            proof = {k: candidate[k] for k in fields if k in candidate}
            current['alternatives'].append(proof)
            full={r['template_role']for r in (current,candidate)if r['classification_status']in QUALIFIED}
            full.update(current.get('conflicting_roles',[]))
            if len(full)>1:
                current.update(role='unknown',classification_status='conflict',
                               reason='contradictory_skin_role_images',conflicting_roles=sorted(full))
            elif current['classification_status']=='cap_only' and candidate['classification_status']in QUALIFIED:
                alternatives = [{k: current[k] for k in fields if k in current},
                                *[r for r in current['alternatives'] if r is not proof]]
                current.clear();current.update(candidate, alternatives=alternatives)
        return account(sorted(retained, key=lambda r: (r['lane'], r['y'],r['role']=='hold_body')),self.by_sampling,self.width,self.height)
