"""Visual note trajectories and frame-bracketed combo events, without per-frame OCR."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from piu_timeline.play.frames import TIME_EPSILON


@dataclass
class Track:
    lane: int
    points: list = field(default_factory=list)
    missed: int = 0
    tracking_observations: list = field(default_factory=list)
    tracking_warnings: list = field(default_factory=list)
    tracking_connections: list = field(default_factory=list)
    coordinate_points: list = field(default_factory=list)


class NoteTracker:
    def __init__(self, layout, width, height, skin_bank=None):
        self.layout, self.width, self.height = layout, width, height
        self.spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
        self.active, self.finished = [], []
        self.hold_candidate, self.unsupported_intervals = False, []
        self.timeline=[]
        self.source_pts={}
        self.skin_detector = None
        self.frame_centers = None
        self.frame_steps = []
        self.skin_observations = []
        if skin_bank is not None:
            from piu_timeline.play.skins.detector import SkinDetector
            self.skin_detector = SkinDetector(skin_bank, layout, width, height)
            from piu_timeline.play.skins.frame_centers import FrameCenters
            self.frame_centers = FrameCenters(self.skin_detector)
            from piu_timeline.play.skins.held import BodyAtReceptor
            self.body_at_receptor = BodyAtReceptor(self.skin_detector)

    def detect(self, rgb):
        if self.skin_detector is not None:
            self.skin_observations = self.skin_detector.detect(rgb)
            self.hold_candidate = self.body_at_receptor(self.skin_observations)
            return [o for o in self.skin_observations if o['role'] != 'hold_body']
        raise ValueError('Image note-skin bank required for note detection')

    def gap_limit(self,track):
        region=self.layout.get('combo_roi')
        if region is not None and len(track.points)>=4:
            x,y,w,h=region;px=self.layout['lanes'][track.lane]['x'];py=track.points[-1][1]/self.height
            if x-.10<=px<=x+w+.10 and y-.18<=py<=y+h+.10:return .35
        return .12

    def observations(self,seconds,detections):
        result=[]
        for image in detections:
            if self.frame_centers is not None:position=self.frame_centers.position(image)
            else:
                # Direct non-image callers provide normalized cap-center coordinates.
                center={'yPixels':image['y']*self.height,'uncertaintyPixels':.5,'basis':{'kind':'native_cap_center'}}
                position={'anchor':center,'center':center}
            result.append({'time':seconds,**position})
        return result

    def update(self, seconds, detections, source_pts=None):
        from piu_timeline.derived import call,CONTRACTS
        observations=self.observations(seconds,detections)
        if source_pts is not None:
            for observation in observations:
                observation['sourcePtsSeconds']=source_pts
                if 'measurement'in observation:observation['measurement'].update(time=seconds,source_pts_seconds=source_pts)
        tracking_view=[{k:v for k,v in o.items()if k!='measurement'}for o in observations]
        self.timeline.append({'time':seconds,'source_pts':source_pts})
        self.source_pts[seconds]=source_pts
        if self.hold_candidate:
            if self.unsupported_intervals and seconds - self.unsupported_intervals[-1]['end_seconds'] < .1:
                self.unsupported_intervals[-1]['end_seconds'] = seconds
            else:
                self.unsupported_intervals.append({'start_seconds': seconds, 'end_seconds': seconds,
                                                   'reason': 'possible_hold_or_dense_stack'})
        assignment=call('frameTracking.assign',
            [{'lane':t.lane,'observations':t.tracking_observations,'maximumGapSeconds':self.gap_limit(t)}for t in self.active],
            [{'lane':n['lane'],'observation':o}for n,o in zip(detections,tracking_view,strict=True)],seconds,self.spacing,[],self.frame_steps)
        self.frame_steps=[s for s in self.frame_steps if seconds-s['toSeconds']<=.35]
        if assignment['step']:self.frame_steps.append(assignment['step'])
        used_tracks, used_notes = set(), set()
        for i,j in assignment['matches']:
            self.active[i].points.append((seconds, detections[j]['y'] * self.height))
            self.active[i].tracking_observations.append(tracking_view[j])
            self.active[i].coordinate_points.append(observations[j])
            history=self.active[i].tracking_observations
            self.active[i].tracking_observations=[o for k,o in enumerate(history)
                if seconds-o['time']<=CONTRACTS['frame_tracking']['identity_history_seconds']+1e-6
                or k>=len(history)-CONTRACTS['frame_tracking']['history_frames']]
            for proof in assignment['gapConnections']:
                if proof['track']==i:self.active[i].tracking_connections.append({**proof,'source_pts_seconds':source_pts})
            self.active[i].missed = 0
            for warning in assignment['cadenceWarnings']:
                before=self.source_pts.get(warning['visible_start_seconds'])
                self.active[i].tracking_warnings.append({**warning,'observed_points':len(assignment['matches']),
                    'source_pts_seconds':[before,source_pts]})
            used_tracks.add(i); used_notes.add(j)
        for i, track in enumerate(self.active):
            if i not in used_tracks:
                track.missed += 1
        uncertain=set(assignment['ambiguousTracks'])
        warning={'reason':'ambiguous_note_tracking','check':'note_visibility',
                 'visible_start_seconds':seconds,'visible_end_seconds':seconds,'source_pts_seconds':[source_pts],
                 'observed_points':len(assignment['ambiguities']),
                 'candidate_frame_displacements':assignment['translationAlternatives'],
                 'candidate_edges':[{'previous_lane':self.active[i].lane,'previous_seconds':self.active[i].points[-1][0],
                    'previous_image_y_pixels':self.active[i].points[-1][1],
                    'observed_lane':detections[j]['lane'],'observed_image_y_pixels':detections[j]['y']*self.height,
                    'current_observation_index':j}for i,j in assignment['ambiguities']]}
        for i in uncertain:self.active[i].tracking_warnings.append(warning)
        expired = [track for i,track in enumerate(self.active)if i in uncertain or seconds-track.points[-1][0]>self.gap_limit(track)]
        self.finished += expired
        self.active = [track for i,track in enumerate(self.active)if i not in uncertain and seconds-track.points[-1][0]<=self.gap_limit(track)]
        for j, note in enumerate(detections):
            if j not in used_notes:
                self.active.append(Track(note['lane'],[(seconds,note['y']*self.height)],
                    tracking_observations=[tracking_view[j]],coordinate_points=[observations[j]],
                    tracking_warnings=[warning]if j in assignment['ambiguousDetections']else[]))

    def finish(self):
        """Finalize visual identities; no crossing clocks or input associations."""
        from piu_timeline.play.fragments import stitch_tracks
        from piu_timeline.play.shared_timing import registered_motion
        import json
        source_tracks=self.finished+self.active
        qualified=[];groups={};unqualified=[]
        for i,track in enumerate(source_tracks):
            records=track.coordinate_points
            if not records or len(records)!=len(track.points):
                unqualified.append(i);continue
            if all(r['center']for r in records):
                positions=[r['center']for r in records]
            elif all(r['anchor']['basis']==records[0]['anchor']['basis']for r in records):
                positions=[r['anchor']for r in records]
            else:
                unqualified.append(i);continue
            basis=json.dumps(positions[0]['basis'],sort_keys=True)
            projected=Track(track.lane,[(r['time'],p['yPixels'])for r,p in zip(records,positions,strict=True)])
            projected.coordinate_basis=positions[0]['basis']['kind']
            projected.registration_uncertainty_pixels=max(p['uncertaintyPixels']for p in positions)
            groups.setdefault(basis,[]).append((i,len(qualified)));qualified.append(projected)
        relative=registered_motion(qualified,self.timeline,self.height,self.spacing,
                                   self.layout['receptor_y']*self.height,self.layout.get('note_y_max',.95)*self.height)
        identities=[([i],None)for i in unqualified]
        for group in groups.values():
            for track,fragments in stitch_tracks([qualified[j]for _,j in group],self.layout['receptor_y']*self.height,
                                                  self.spacing,motion=relative,layout=self.layout):
                identities.append(([group[j][0]for j in fragments],getattr(track,'fragment_connections',None)))
        identities.sort(key=lambda pair:min(pair[0]))
        notes=[]
        for fragments,proof in identities:
            raw=sorted([p for i in fragments for p in source_tracks[i].points])
            note={'lane':source_tracks[fragments[0]].lane,'points':[list(p)for p in raw]}
            measurements=[r['measurement']for i in fragments for r in source_tracks[i].coordinate_points if 'measurement'in r]
            if len(measurements)==len(raw):note['coordinate_measurements']=sorted(measurements,key=lambda r:r['time'])
            warnings=[w for i in fragments for w in source_tracks[i].tracking_warnings]
            connections=[p for i in fragments for p in source_tracks[i].tracking_connections]
            if warnings:note['tracking_warnings']=warnings
            if connections:note['tracking_connections']=connections
            if len(fragments)>1:
                note.update(tracking_method='corroborated_fragments',source_track_fragments=fragments)
                if proof:note['fragment_connections']=proof
            notes.append(note)
        return notes


def fit_track(track, receptor_y, spacing, motion=None, layout=None):
    from piu_timeline.derived import call
    if motion is not None:
        shared=motion.fit(track,receptor_y,layout)
        if shared is not None:
            return {'lane':track.lane,'points':[[float(t),float(y)]for t,y in track.points],**shared}
    return call('tracks.fitTrack',{'lane':track.lane,'points':track.points,
        'registration_uncertainty_pixels':getattr(track,'registration_uncertainty_pixels',0)},receptor_y,spacing)



def glyphs(rgb, threshold=175):
    """Segment white combo digits; reject noise instead of guessing a number."""
    binary = ((rgb.min(axis=2) > threshold) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)).astype('uint8')
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    components = []
    for label, (x, y, w, h, area) in enumerate(stats[1:count], 1):
        if h >= rgb.shape[0] * .40 and h <= rgb.shape[0] * .98 and area >= 8 and w <= rgb.shape[1] * .4:
            components.append((int(x), (labels[y:y+h, x:x+w] == label).astype('uint8')))
    components.sort(key=lambda item: item[0])
    if not 1 <= len(components) <= 5:
        return []
    normalized = []
    for _, component in components:
        h, w = component.shape
        scale = min(18 / w, 28 / h)
        resized = cv2.resize(component, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_NEAREST)
        canvas = np.zeros((32, 22), dtype='uint8')
        top, left = (32 - resized.shape[0]) // 2, (22 - resized.shape[1]) // 2
        canvas[top:top+resized.shape[0], left:left+resized.shape[1]] = resized
        normalized.append(canvas)
    return normalized


class DigitReader:
    def __init__(self):
        self.examples = {str(i): [] for i in range(10)}
        self.sources = {str(i): set() for i in range(10)}
        self.training_call = 0
        self._comparison = None

    def train(self, rgb, value, source=None):
        self.training_call += 1
        source = str(source if source is not None else self.training_call)
        digits = glyphs(rgb)
        text = str(value)
        if len(digits) != len(text) or not text.isdigit():
            return False
        # Contradicting a strongly recognized existing glyph must not poison
        # the font bank when neural OCR misreads stylized counter text.
        if any(self._read_digits([image], None)[0] not in (None, int(digit))
               and self._read_digits([image], None)[1] >= .9 for digit,image in zip(text,digits)):
            return False
        for digit, image in zip(text, digits):
            self.examples[digit] = (self.examples[digit] + [image])[-24:]
            self.sources[digit].add(source)
        self._comparison = None
        return True

    def save(self, path):
        arrays = {}
        for digit, examples in self.examples.items():
            arrays['digit_' + digit] = np.asarray(examples, dtype='uint8').reshape(-1, 32, 22)
            arrays['sources_' + digit] = np.asarray(sorted(self.sources[digit]), dtype=str)
        np.savez_compressed(path, **arrays)

    @classmethod
    def load(cls, path):
        reader = cls()
        with np.load(path, allow_pickle=False) as bank:
            for digit in reader.examples:
                reader.examples[digit] = list(bank['digit_' + digit])
                reader.sources[digit] = set(bank['sources_' + digit].tolist())
        return reader

    def read(self, rgb, expected=None, recover=True):
        primary = self._read_digits(glyphs(rgb), expected)
        if primary[0] is not None or not recover:
            return primary
        options = []
        for threshold in (190, 205):
            result = self._read_digits(glyphs(rgb, threshold), expected)
            if result[0] is not None and result[1] >= .82:
                options.append(result)
        if options and len({value for value,_ in options}) == 1:
            self.last_mode = 'threshold_template'
            return max(options, key=lambda result: result[1])
        if not options:
            from piu_timeline.play.counter_pixels import contrast_thresholds
            contrast=[self._read_digits(glyphs(rgb,t),None)for t in contrast_thresholds(rgb)]
            if (len(contrast)==2 and all(value is not None and score>=.82 for value,score in contrast)
                    and len({value for value,_ in contrast})==1):
                self.last_mode='contrast_template'
                return min(contrast,key=lambda result:result[1])
        self.last_mode = 'unreadable'
        return None, 0.0

    def _read_digits(self, digits, expected):
        self.last_mode = 'unreadable'
        if not digits:
            return None, 0.0
        if self._comparison is None:
            examples, labels = [], []
            for digit, images in self.examples.items():
                if len(self.sources[digit]) >= 2:
                    examples.extend(images)
                    labels.extend([digit]*len(images))
            templates = np.asarray(examples, dtype='uint8').reshape(-1,32,22)
            self._comparison = templates, templates.sum(axis=(1,2)), np.asarray(labels)
        templates, sizes, labels = self._comparison
        distributions = []
        for image in digits:
            overlaps = 2*np.count_nonzero(templates & image, axis=(1,2))/np.maximum(1,sizes+image.sum())
            scores = {digit: float(overlaps[labels == digit].max()) for digit in set(labels)}
            distributions.append(scores)
        ranked = [sorted(scores.items(), key=lambda pair: pair[1], reverse=True) for scores in distributions]
        if all(scores and scores[0][1] >= .82 and (len(scores) == 1 or scores[0][1]-scores[1][1] >= .035)
               for scores in ranked):
            self.last_mode = 'independent_template'
            return int(''.join(scores[0][0] for scores in ranked)), min(scores[0][1] for scores in ranked)
        if expected is None:
            return None, 0.0
        # A nearby counter value may disambiguate a glyph, but every glyph must
        # still visually agree. Never fill an absent or unsegmented counter.
        options = []
        for value in set(range(expected, expected+11)) | set(range(10)):
            text = str(value)
            if len(text) != len(digits):
                continue
            scores = [distribution.get(digit, 0) for distribution,digit in zip(distributions,text)]
            if min(scores) >= .78:
                options.append((sum(scores)/len(scores), min(scores), value))
        options.sort(reverse=True)
        if options and (len(options) == 1 or options[0][0]-options[1][0] >= .035/len(digits)):
            self.last_mode = 'temporal_template'
            return options[0][2], options[0][1]
        return None, 0.0


class ComboTracker:
    def __init__(self):
        self.stable = None
        self.last_seen = None
        self.pending = None
        self.events = []
        self.observations = []

    def update(self, seconds, value, confidence=None, read_mode=None, source_pts=None):
        if value is None:
            return
        self.observations.append({'playback_seconds':seconds,'value':value,'confidence':confidence or 0,
                                  'read_mode':read_mode,'source_pts_seconds':source_pts})
        # Impossible positive jumps and high-valued backwards reads are usually
        # split/misclassified glyphs. They must not replace the stable baseline.
        if self.stable is not None and value != self.stable:
            elapsed = seconds - self.last_seen
            if value - self.stable > max(10, 50 * elapsed) or value < self.stable and value > 10:
                return
        if value == self.stable:
            self.last_seen = seconds
            self.pending = None
            return
        if self.pending is None or self.pending['value'] != value:
            self.pending = {'value': value, 'first': seconds, 'previous': self.last_seen}
            return
        previous = self.pending['previous']
        if self.stable is not None and previous is not None:
            delta = value - self.stable
            bounded = 1 <= delta <= 10 and self.pending['first']-previous <= .1+TIME_EPSILON
            self.events.append({'before': self.stable, 'after': value, 'delta': delta,
                                'lower_seconds': previous, 'upper_seconds': self.pending['first'],
                                'confirmation_seconds':seconds,
                                'status': 'candidate' if bounded else 'excluded',
                                'reason': None if bounded
                                else 'combo_reset' if delta <= 0 else 'combo_jump_or_observation_gap'})
        self.stable, self.last_seen, self.pending = value, seconds, None


def associate(notes,combo_events,window=.045,display_delay=0.0,event_note_constraints=None):
    from piu_timeline.derived import call
    fields=('lane','status','target_seconds')
    return call('association.associate',[{k:n[k]for k in fields if k in n}for n in notes],
                combo_events,window,display_delay,event_note_constraints,mutated=(1,))


def collect_tracks(tracker,combo,directory,source):
    """Persist visual identities and independent counter events, without timing fits."""
    from pathlib import Path
    result={'notes':tracker.finish(),'frame_timeline':[
        {'time':s['time'],'source_pts':s['source_pts']}for s in tracker.timeline],
        'unsupported_intervals':tracker.unsupported_intervals,'combo_events':combo.events,'counter_observations':combo.observations,'tracking_complete':True,'coordinate_measurement_contract':source.get('skin_detector',{}).get('contract')}
    from piu_timeline.play.observations.artifacts import save_input
    from piu_timeline.play.stages import fingerprint
    from piu_timeline.derived import CONTRACTS
    identity={'source':{k:source.get(k)for k in ('media','game_roi','start_seconds','end_seconds')},
              'geometry':{'width':tracker.width,'height':tracker.height,'layout':tracker.layout},
              'detector_contract':source.get('skin_detector',{}).get('contract'),
              'frame_observations_sha256':source.get('frame_observations_sha256'),
              'object_roles':source.get('object_interpretation',{}).get('contract'),
              'tracking_contract':CONTRACTS['frame_tracking'],'fragment_contract':CONTRACTS['fragments']}
    save_input(Path(directory)/'counter-events.json',{'schema':1,'events':combo.events,'observations':combo.observations})
    save_input(Path(directory)/'tracking.json',{'schema':1,'stage':'visual-tracks','input_fingerprint':fingerprint(identity),'input':identity,
               'notes':result['notes'],'timeline':result['frame_timeline']})
    return result



def replay(data,directory,bank,tracker=None):
    """Assign identities from saved frames without image acquisition or target fitting."""
    import json
    from piu_timeline.play.observations.cache import tracking_notes,validate_native_frame
    tracker=tracker or NoteTracker(data['layout'],data['analysis_width'],data['analysis_height'],skin_bank=bank)
    from hashlib import sha256
    digest=sha256()
    combo=ComboTracker();count=0;last=None
    with (directory/'frames.jsonl').open('rb')as stream:
        for line in stream:
            digest.update(line)
            frame=json.loads(line);validate_native_frame(frame,len(data['layout']['lanes']))
            seconds=frame['playback_seconds']
            if last is not None and seconds<=last:raise ValueError('Saved observation timestamps are not increasing')
            last=seconds;count+=1
            tracker.hold_candidate=frame.get('possible_hold_or_dense_stack',False)
            tracker.update(seconds,tracking_notes(frame),frame['source_pts_seconds'])
            combo.update(seconds,frame['combo'],frame.get('combo_confidence'),frame.get('combo_read_mode'),frame['source_pts_seconds'])
    if count!=data['frame_count']:raise ValueError('Saved native-frame observations are incomplete')
    return collect_tracks(tracker,combo,directory,{**data,'frame_observations_sha256':digest.hexdigest()})
