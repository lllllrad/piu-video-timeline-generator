"""Collect a bounded review queue without discarding native warning artifacts."""
from collections import defaultdict
from hashlib import sha256
from itertools import zip_longest
import json


class WarningBatch:
    def __init__(self, limit, reviewed=()):
        if limit is not None and limit<1:
            raise ValueError('Warning limit must be positive')
        self.limit=limit
        self.seen=set(reviewed)
        self.reviewed_count=len(self.seen)
        self.items=[]

    @property
    def full(self):
        return self.limit is not None and len(self.items)>=self.limit

    def collect(self, directory, source, segment):
        if self.limit is None or self.full:return
        records=[(item,'recognition-warnings.json') for item in
                 json.loads((directory/'recognition-warnings.json').read_text())['warnings']]
        excluded=directory/'excluded-trajectories.json'
        if excluded.is_file():
            records.extend((item,excluded.name) for item in json.loads(excluded.read_text())['warnings'])
        groups=defaultdict(list)
        for item,artifact in records:groups[item['reason']].append((item,artifact))
        # Represent different failure types before filling the queue with repeats.
        for row in zip_longest(*groups.values()):
            for entry in row:
                if entry is None:continue
                item,artifact=entry
                identity={key:item.get(key) for key in ('reason','note','lane','visible_start_seconds','visible_end_seconds')}
                key=sha256(json.dumps([source,segment,identity],sort_keys=True).encode()).hexdigest()
                if key in self.seen:continue
                self.seen.add(key)
                self.items.append({'id':key,'source':source,'segment':segment,'warning':item,'artifact':artifact,
                                   'report':str(directory/'report.html')})
                if self.full:return

    def document(self):
        return {'limit':self.limit,'previously_reviewed_cases':self.reviewed_count,'collected':len(self.items),'limit_reached':self.full,'items':self.items,
                'semantics':'Distinct unresolved cases collected in this run. Original warning files retain all remaining cases; this queue does not acknowledge, suppress or delete them.'}
