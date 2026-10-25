"""Read native judgment words and observe their animation refreshes."""
import cv2
import numpy as np

LABELS = ('PERFECT', 'GREAT', 'GOOD', 'BAD', 'MISS')


def feature_map(rgb):
    hsv = cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    h,s,v = cv2.split(hsv)
    result = np.full(h.shape,255,dtype='uint8')
    colored = (s>90)&(v>155)
    result[colored] = h[colored]//10
    result[(s<70)&(v>190)] = 18
    return result


def color_mask(feature, hue):
    if hue == 18:
        return (feature==18).astype('uint8')
    distance = np.abs(feature.astype('int16')-hue)
    return ((feature<18)&(np.minimum(distance,18-distance)<=1)).astype('uint8')


class JudgmentReader:
    def __init__(self, models):
        self.templates=[]
        self.partial_templates=[]
        aspects={label:[len(m['mask'][0])/len(m['mask']) for m in models if m['label']==label] for label in LABELS}
        for model in models:
            mask=np.asarray(model['mask'],dtype='float32')
            h,w=mask.shape
            family=aspects[model['label']]
            if len(family)>=3 and abs(w/h/float(np.median(family))-1)>.20:
                continue
            normalized=cv2.resize(mask,(max(8,round(w/h*24)),24),interpolation=cv2.INTER_LINEAR)
            self.templates.append((model['label'],model['hue'],w/h,h,normalized))
            # The launch animation shrinks below the sampled template size.
            # A touching note can defeat component bounds at those smaller
            # scales too; preserve the same shape/coverage tests there.
            for scale in (.7,.8,.9,1.,1.1,1.2,1.4):
                scaled=cv2.resize(mask,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_LINEAR)
                self.partial_templates.append((model['label'],model['hue'],scaled))

    def read_partial(self, feature, masks):
        """Locate the word itself when a touching note corrupts its component."""
        scores={}
        height,width=feature.shape
        for label,hue,template in self.partial_templates:
            h,w=template.shape
            left=max(0,round((width-w)/2-width*.10));right=min(width,round((width+w)/2+width*.10))
            top=round(height*.20);bottom=round(height*.82)
            if bottom-top<h or right-left<w:continue
            if hue not in masks:masks[hue]=color_mask(feature,hue)
            search=masks[hue][top:bottom,left:right].astype('float32')
            correlation=cv2.matchTemplate(search,template,cv2.TM_CCORR_NORMED)
            _,score,_,(x,y)=cv2.minMaxLoc(correlation)
            if score<.83:continue
            crop=search[y:y+h,x:x+w]
            # Most of the word must independently retain its letter shapes.
            # A small matching patch or a solid same-color object is insufficient.
            pieces=[]
            for a,b in zip(np.linspace(0,w,5,dtype=int)[:-1],np.linspace(0,w,5,dtype=int)[1:]):
                observed,expected=crop[:,a:b],template[:,a:b]
                pieces.append(float(2*np.sum(observed*expected)/max(1e-6,np.sum(observed**2)+np.sum(expected**2))))
            if sum(value>=.80 for value in pieces)<3:continue
            if score>scores.get(label,(-1,None))[0]:scores[label]=score,[x+left,y+top,w,h]
        ranked=sorted(scores.items(),key=lambda pair:pair[1][0],reverse=True)
        if not ranked or len(ranked)>1 and ranked[0][1][0]-ranked[1][1][0]<.08:
            return None
        label,(score,box)=ranked[0]
        return {'label':label,'confidence':score,'box':box,'blank':False,'read_mode':'partial_template'}

    def read(self, feature):
        masks,boxes,scores={}, {}, {}
        for label,hue,aspect,native_height,template in self.templates:
            if hue not in masks:
                mask=color_mask(feature,hue)
                masks[hue]=mask
                joined=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((1,9),dtype='uint8'))
                _,_,stats,_=cv2.connectedComponentsWithStats(joined,8)
                boxes[hue]=[(int(x),int(y),int(w),int(h)) for x,y,w,h,area in stats[1:]
                            if w>=10 and 4<=h<feature.shape[0]*.72
                            and abs(x+w/2-feature.shape[1]/2)<feature.shape[1]*.18
                            and y+h/2<feature.shape[0]*.80]
            for x,y,w,h in boxes[hue]:
                if abs(w/h/aspect-1)>.25 or not .65*native_height<=h<=1.65*native_height:
                    continue
                mask=masks[hue][y:y+h,x:x+w].astype('float32')
                normalized=cv2.resize(mask,(template.shape[1],24),interpolation=cv2.INTER_LINEAR)
                score=float(2*np.sum(normalized*template)/max(1e-6,np.sum(normalized**2)+np.sum(template**2)))
                if score>scores.get(label,(-1,None))[0]:scores[label]=score,[x,y,w,h]
        ranked=sorted(scores.items(),key=lambda pair:pair[1][0],reverse=True)
        if not ranked or ranked[0][1][0]<.72 or len(ranked)>1 and ranked[0][1][0]-ranked[1][1][0]<.08:
            partial=self.read_partial(feature,masks)
            if partial is not None:return partial
            return {'label':None,'confidence':0.,'box':None,
                    'blank':bool(masks) and all(np.count_nonzero(mask)<12 for mask in masks.values())}
        label,(confidence,box)=ranked[0]
        return {'label':label,'confidence':confidence,'box':box,'blank':False,'read_mode':'component_template'}


class JudgmentTracker:
    def __init__(self):
        self.last = None
        self.pending = None
        self.last_visible = None
        self.last_frame = None
        self.events = []
        self.blank_since = None
        self.last_clear = None

    def update(self, seconds, observation):
        label = observation['label']
        if label is None:
            if observation.get('blank'):
                if self.blank_since is None:self.blank_since=seconds
                self.last_clear=seconds
            else:
                self.blank_since=None
            self.last_frame = seconds
            return
        box = observation['box']
        changed = self.last is None or label!=self.last['label']
        gap = self.blank_since is not None and seconds-self.blank_since>=.10
        relaunch = False
        if self.last is not None and not changed and self.last.get('box') and box:
            old = self.last['box']
            sx,sy=box[2]/old[2],box[3]/old[3]
            relaunch = (sx*sy>1.25 and sx>1.10 and abs(sx/sy-1)<.20
                        and self.last_visible is not None and seconds-self.last_visible<=.035)
        if self.pending is not None:
            same = label==self.pending['label']
            if self.pending['trigger']=='animation_restart' and box:
                same = same and box[2]>=self.pending['launch_width']*.88
            if same and seconds-self.pending['upper_seconds']<=.075:
                event = {key:value for key,value in self.pending.items() if key!='launch_width'}
                valid=event['lower_seconds'] is not None and event['upper_seconds']-event['lower_seconds']<=.1
                if event['lower_seconds'] is None:event['lower_seconds']=event['upper_seconds']
                event.update(status='candidate' if valid else 'excluded',reason=None if valid else 'judgment_observation_gap',
                             detection_status='candidate' if valid else 'excluded',
                             detection_reason=None if valid else 'judgment_observation_gap',delta=1)
                self.events.append(event)
                self.pending = None
                self.last = observation
            else:
                self.pending = None
        elif changed or gap or relaunch:
            evidence=[t for t in (self.last_visible,self.last_clear) if t is not None]
            self.pending = {'label':label,'lower_seconds':max(evidence) if evidence else None,
                            'upper_seconds':seconds,'launch_width':box[2] if box else 0,'trigger':'label_change' if changed else 'reappearance' if gap else 'animation_restart'}
        self.blank_since = None
        self.last_visible = seconds
        self.last_frame = seconds
        if self.pending is None:
            self.last = observation
