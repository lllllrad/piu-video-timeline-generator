"""Validate reusable digit shapes against current pixels, never transfer counters."""
import json
from pathlib import Path
import shutil

from .play_tracking import DigitReader


def quality(reader, images):
    reads = [reader.read(image) for image in images]
    strong = [(value,score) for value,score in reads if value is not None and score >= .9]
    labels = set(''.join(str(value) for value,score in strong))
    return len(strong),len(labels),sum(score for value,score in strong)/max(1,len(strong))


def validated_reader(reader, images, data_root, record, destination):
    """Require broad, strong agreement with this recording before importing a font."""
    current = quality(reader, images)
    # A complete, visually validated local font needs no cross-recording search.
    if min(map(len,reader.sources.values())) >= 2 and current[0] >= 6 and current[1] >= 6:
        return reader,None
    best = current; selected = None
    for path in sorted(Path(data_root).glob('*/play/segment-???/evidence/digit-templates.npz')):
        metadata = path.parents[1]/'analysis.json'
        if not metadata.is_file():
            continue
        saved = json.loads(metadata.read_text())
        origin = saved.get('media',{})
        if origin.get('path') == record.get('path'):
            continue
        candidate = DigitReader.load(path)
        if min(map(len,candidate.sources.values())) < 2:
            continue
        score = quality(candidate,images)
        if score[0] < max(6,current[0]+3) or score[1] < 6 or score <= best:
            continue
        best = score;selected=(candidate,path,origin)
    if selected is None:
        return reader,None
    candidate,path,origin = selected
    imported = destination/'validated-font.npz' if destination is not None else path
    if destination is not None:
        shutil.copyfile(path,imported)
    return candidate,{'kind':'pixel_validated_font','source_media':origin.get('path'),
                      'template_archive':str(imported),'validation_frames':best[0],
                      'validation_digit_classes':best[1],
                      'minimum_validation_confidence':.9,
                      'semantics':'Only glyph shapes and their training provenance are imported; counter values and observation times are read from the current recording.'}


def saved_inputs(output):
    import cv2
    evidence=output/'evidence';bank=evidence/'digit-templates.npz'
    if not bank.is_file():
        return None, []
    images=[cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
            for path in sorted(evidence.glob('combo-[0-9][0-9].png'))]
    return DigitReader.load(bank), images


def cache_current(cached, output, data_root):
    """A newly available, pixel-validated font can improve an existing cache."""
    reader, images = saved_inputs(output)
    if reader is None or not images:
        return True
    _, provenance = validated_reader(reader, images, data_root, cached['media'], None)
    return provenance is None


def refresh_reader(cached, output, data_root):
    """Revalidate saved bootstrap crops without decoding or neural OCR."""
    reader, images = saved_inputs(output)
    if reader is None:
        return False
    evidence=output/'evidence';bank=evidence/'digit-templates.npz'
    reader,provenance=validated_reader(reader,images,data_root,cached['media'],evidence)
    if provenance is None:
        return False
    reader.save(bank)
    saved=evidence/'bootstrap.json'
    if saved.is_file():
        document=json.loads(saved.read_text());document['reused_from']=provenance
        saved.write_text(json.dumps(document,indent=2)+'\n')
    cached['bootstrap']={**cached.get('bootstrap',{}),'reused_from':provenance,
                         'missing_digits':[digit for digit,sources in reader.sources.items() if len(sources)<2],
                         'template_counts':{digit:len(sources) for digit,sources in reader.sources.items()}}
    return True
