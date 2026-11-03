"""Certify generated reference geometry independently of any moving scene."""
from hashlib import sha256
import json

import cv2

from piu_timeline.play.skins.anchors import certificate
from piu_timeline.play.skins.bank import load_bank


def certify(path):
    document=json.loads(path.read_text())
    # Each generated glyph is drawn about its declared anchor. These reference
    # images, not scene object identities or target times, define its center.
    for entry in document['templates']:
        if entry['role']=='hold_body':continue
        image=path.parent/entry['image'];stat=image.stat()
        height,width=cv2.imread(str(image)).shape[:2]
        entry['source_evidence']={'media':{'path':str(image),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns},
            'reference_dimensions':[width,height],'source_crop':[0,0,width,height],
            'playback_seconds':0.,'source_pts_seconds':0.}
    path.write_text(json.dumps(document));bank=load_bank(path)
    templates={t['id']:t for t in bank['templates']}
    for entry in document['templates']:
        if entry['role']=='hold_body':continue
        template=templates[entry['id']];evidence=entry['source_evidence']
        entry['native_anchor_registration']=certificate(bank,template,
            {'time':0.,'source_pts_seconds':0.,'detected_y_pixels':entry['anchor_pixels'][1],'offset_pixels':0.},
            evidence['source_crop'],sha256((path.parent/entry['image']).read_bytes()).hexdigest(),
            sha256(template['rgb'].tobytes()).hexdigest())
    path.write_text(json.dumps(document))
    return load_bank(path)
