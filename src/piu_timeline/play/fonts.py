"""Validate reusable digit shapes against current pixels, never transfer counters."""
import json
from pathlib import Path
import shutil
import re

import cv2
import numpy as np

from piu_timeline.play.frames import crop_region
from piu_timeline.metadata.recognition import capture_game
from piu_timeline.vision.ocr import ocr_images
from piu_timeline.workflow import LOCAL_DATA

from piu_timeline.play.tracking import DigitReader


def quality(reader, images):
    reads = [reader.read(image) for image in images]
    strong = [(value,score) for value,score in reads if value is not None and score >= .9]
    labels = set(''.join(str(value) for value,score in strong))
    return len(strong),len(labels),sum(score for value,score in strong)/max(1,len(strong))


def validated_reader(reader, images, data_root, record, destination, settings=None):
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
        same_recording = origin == record
        provenance = saved.get('bootstrap', {}).get('reused_from') or {}
        same_geometry = (settings is not None and saved.get('game_roi') == settings.get('game_roi')
                         and saved.get('analysis_width') == settings.get('analysis_width'))
        trusted_recording_font = (same_recording and same_geometry
                                  and provenance.get('kind') == 'pixel_validated_font'
                                  and provenance.get('validation_frames', 0) >= 6
                                  and provenance.get('validation_digit_classes', 0) >= 6)
        if origin.get('path') == record.get('path') and not trusted_recording_font:
            continue
        candidate = DigitReader.load(path)
        if min(map(len,candidate.sources.values())) < 2:
            continue
        score = quality(candidate,images)
        minimum_frames, minimum_classes, improvement = (2,5,2) if trusted_recording_font else (6,6,3)
        if score[0] < max(minimum_frames,current[0]+improvement) or score[1] < minimum_classes or score <= best:
            continue
        best = score;selected=(candidate,path,origin,trusted_recording_font)
    if selected is None:
        return reader,None
    candidate,path,origin,trusted_recording_font = selected
    imported = destination/'validated-font.npz' if destination is not None else path
    if destination is not None:
        shutil.copyfile(path,imported)
    return candidate,{'kind':'recording_validated_font' if trusted_recording_font else 'pixel_validated_font','source_media':origin.get('path'),
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
    _, provenance = validated_reader(reader, images, data_root, cached['media'], None, cached)
    return provenance is None


def refresh_reader(cached, output, data_root):
    """Revalidate saved bootstrap crops without decoding or neural OCR."""
    reader, images = saved_inputs(output)
    if reader is None:
        return False
    evidence=output/'evidence';bank=evidence/'digit-templates.npz'
    reader,provenance=validated_reader(reader,images,data_root,cached['media'],evidence,cached)
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


def previous_digit_reader(directory, record):
    """Reuse font examples, never counter values or timestamps from another play."""
    root = directory.parent.parent
    for previous in sorted(root.glob('segment-*/analysis.json')):
        if not re.fullmatch(r'segment-\d{3}', previous.parent.name):
            continue
        saved = json.loads(previous.read_text())
        if any(saved.get('media', {}).get(key) != record.get(key) for key in ('path', 'size_bytes', 'mtime_ns')):
            continue
        bank = previous.parent / 'evidence/digit-templates.npz'
        if bank.is_file():
            reader = DigitReader.load(bank)
            imported = directory / 'imported-digit-templates.npz'
            shutil.copyfile(bank, imported)
            return reader, {'template_archive': str(imported), 'source_media': record['path'],
                            'source_pts_by_digit': {digit: sorted(times) for digit,times in reader.sources.items()}}
        evidence = previous.parent / 'evidence/bootstrap.json'
        if not evidence.is_file():
            continue
        bootstrap = json.loads(evidence.read_text())
        labels = {label['source_pts_seconds']: label['text'] for label in bootstrap.get('labels', []) if label['accepted']}
        reader = DigitReader()
        for frame in bootstrap.get('frames', []):
            text = labels.get(frame['source_pts_seconds'])
            if text is None or not Path(frame['file']).is_file():
                continue
            image = cv2.cvtColor(cv2.imread(frame['file']), cv2.COLOR_BGR2RGB)
            crop = crop_region(image, saved['layout']['combo_roi'])
            reader.train(crop, text, source=frame['source_pts_seconds'])
            scale = saved['analysis_width'] / image.shape[1]
            reader.train(cv2.resize(crop, (round(crop.shape[1]*scale), round(crop.shape[0]*scale))),
                         text, source=frame['source_pts_seconds'])
        if all(len(sources) >= 2 for sources in reader.sources.values()):
            return reader, {'source_media': record['path'], 'ocr_labels': bootstrap.get('labels', []),
                            'source_pts_by_digit': {digit: sorted(times) for digit,times in reader.sources.items()}}
    return DigitReader(), None


def bootstrap_digits(record, roi, start, end, layout, directory, width=650, samples=32):
    directory.mkdir(parents=True, exist_ok=True)
    reader, reused_from = previous_digit_reader(directory, record)
    crops, images, metadata, labels = [], [], [], []
    if reused_from:
        samples = min(samples, 8)
    for i, seconds in enumerate(np.linspace(start + (end-start)*.08, end - (end-start)*.05, samples)):
        path = directory / f'combo-source-{i:02}.png'
        frame = capture_game(record, path, float(seconds), roi)
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        crop = crop_region(rgb, layout['combo_roi'])
        from piu_timeline.play.tracking import glyphs
        if not glyphs(crop):
            continue
        crop_path = directory / f'combo-{i:02}.png'
        cv2.imwrite(str(crop_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        crops.append(crop_path); images.append(crop); metadata.append(frame)
    reader, validated = validated_reader(reader, images, LOCAL_DATA, record, directory,
                                        {'game_roi':list(roi),'analysis_width':width})
    if validated is not None:
        reused_from = validated
        print(f'  Reusing a pixel-validated digit font ({validated["validation_frames"]} current frames); no counter values transferred.', flush=True)
    unknown = [i for i,image in enumerate(images) if reader.read(image)[0] is None] if validated is None else []
    for result, i in zip(ocr_images([crops[i] for i in unknown], english=True) if unknown else [], unknown):
        image, frame = images[i], metadata[i]
        lines = sorted(result['lines'], key=lambda line: line['box'][0])
        tokens = [line['text'].strip() for line in lines if re.fullmatch(r'\d{1,5}', line['text'].strip()) and line['confidence'] >= .5]
        text = ''.join(tokens)
        if text and len(text) <= 5:
            accepted = reader.train(image, text, source=frame['source_pts_seconds'])
            labels.append({'source_pts_seconds': frame['source_pts_seconds'], 'text': text,
                           'accepted': accepted, 'ocr': lines})
            scale = width / roi[2]
            small = cv2.resize(image, (max(1, round(image.shape[1]*scale)), max(1, round(image.shape[0]*scale))), interpolation=cv2.INTER_AREA)
            reader.train(small, text, source=frame['source_pts_seconds'])
    counts = {digit: len(sources) for digit, sources in reader.sources.items()}
    # Keep the full-resolution source examples and their exact PTS for review.
    (directory / 'bootstrap.json').write_text(json.dumps({'frames': metadata, 'template_counts': counts,
                                                         'ocr_images': len(unknown), 'labels': labels, 'reused_from': reused_from}, indent=2) + '\n')
    reader.save(directory / 'digit-templates.npz')
    return reader, {'template_counts': counts, 'ocr_images': len(unknown), 'reused_from': reused_from,
                    'missing_digits': [digit for digit, n in counts.items() if n < 2]}
