from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from piu_timeline import ucs
from piu_timeline.chart_data import draft, initialize, register, resolve_code, remember_alias, auto_register
from piu_timeline.official_ucs import catalogue_cells, read_archive, parse_catalogue


TEMPLATE = ':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=2\n' + '.....\n'*16
CATALOGUE = {'schema': 1, 'songs': [{'index': 'CS349', 'title': 'CHAOS AGAIN', 'artist': 'NAOKI underground'}]}


class Provider:
    def catalogue(self):
        return CATALOGUE

    def template(self, code):
        return ucs.parse(TEMPLATE), Path('unused.mp3'), 'https://ucs.piugame.com/sample_download/zip.php?ucs_index='+code


def data():
    return {'song': 'CHAOS AGAIN', 'chart': 'S21', 'segment_number': 1,
            'media': {'size_bytes': 123, 'mtime_ns': 456}, 'start_seconds': 10, 'end_seconds': 14,
            'layout': {'lanes': [{}]*5}, 'matches': [], 'combo_events': [], 'judgment_events': [],
            'notes': [{'status': 'estimated', 'lane': lane, 'target_seconds': target,
                       'prediction_uncertainty_seconds': .01} for lane, target in ((0, 10.5), (1, 11), (2, 11.5))]}


class ChartDataTest(unittest.TestCase):
    def test_constant_tempo_template_can_extend_without_moving_original_rows(self):
        source = data()
        source['end_seconds'] = 25
        source['notes'].append({'status': 'estimated', 'lane': 4, 'target_seconds': 22,
                                'prediction_uncertainty_seconds': .01})
        alignment = {'song_start_seconds': 10, 'uncertainty_seconds': 0}
        _, incomplete = draft(ucs.parse(TEMPLATE), source, alignment)
        self.assertEqual(incomplete['summary']['unresolved_note_heads'], 1)
        doc, complete = draft(ucs.parse(TEMPLATE), source, alignment, extend_constant_tempo=True)
        self.assertEqual(complete['summary']['unresolved_note_heads'], 0)
        self.assertTrue(complete['timing_extension']['review_required'])
        self.assertEqual(complete['summary']['placed_taps'], 4)
        grid = list(doc.grid())
        self.assertIn((0, 1152, 12), grid)
        self.assertEqual(doc.sections[0].rows[1152], '....X')
        for si, ri, time in ucs.parse(TEMPLATE).grid():
            self.assertIn((si, ri*24, time), grid)

    def test_explicit_rebuild_preserves_backup_and_refuses_reviewed_or_edited_chart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = initialize(root/'repo', Provider()); output = root/'video/play/segment-001'
            output.mkdir(parents=True)
            result = register(data(), output, repository=repo, song_start=10, client=Provider())
            chart = Path(result['chart']); original = chart.read_bytes()
            result = register(data(), output, repository=repo, song_start=10, client=Provider(), rebuild_draft=True)
            self.assertEqual(result['status'], 'rebuilt')
            backup = next(chart.parent.parent.glob('phoenix.build-previous-*'))
            self.assertEqual((backup/'chart.ucs').read_bytes(), original)
            chart.write_text(chart.read_text().replace('X....', '....X', 1))
            with self.assertRaisesRegex(ValueError, 'manually edited'):
                register(data(), output, repository=repo, song_start=10, client=Provider(), rebuild_draft=True)
            chart.write_bytes(original)
            metadata = chart.with_name('metadata.json'); saved = json.loads(metadata.read_text())
            saved['review_status'] = 'reviewed'; metadata.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, 'reviewed'):
                register(data(), output, repository=repo, song_start=10, client=Provider(), rebuild_draft=True)

    def test_taps_holds_and_double_rows_preserve_song_timing(self):
        source = data()
        source['chart'] = 'D22'; source['layout']['lanes'] = [{}]*10
        source['hold_analysis'] = {'holds': [{'id': 0, 'lane': 1, 'start_range': [10.99, 11.01], 'end_range': [11.99, 12.01],
                                             'start_censored': False, 'end_censored': False, 'head_note': 1,
                                             'covered_notes': [1], 'input': {'segments': []}}]}
        original = deepcopy(source)
        document, evidence = draft(ucs.parse(TEMPLATE), source, {'song_start_seconds': 10, 'uncertainty_seconds': .01})
        self.assertEqual(source, original)
        self.assertEqual(document.mode, 'Double')
        rows = [(float(t), document.sections[si].rows[ri]) for si, ri, t in document.grid()]
        self.assertIn((.5, 'X.........'), rows)
        self.assertIn((1, '.M........'), rows)
        self.assertIn((2, '.W........'), rows)
        self.assertTrue(any(1 < t < 2 and row[1] == 'H' for t, row in rows))
        self.assertEqual(evidence['summary']['placed_holds'], 1)
        self.assertEqual(evidence['summary']['placed_taps'], 2)
        self.assertEqual(ucs.parse(document.text()), document)

    def test_collision_and_censored_hold_remain_unresolved(self):
        source = data()
        source['notes'][1].update(lane=0, target_seconds=10.5)
        source['hold_analysis'] = {'holds': [{'id': 0, 'lane': 2, 'start_range': [11.49, 11.51], 'end_range': None,
                                             'start_censored': False, 'end_censored': True, 'head_note': 2,
                                             'last_body_seconds': 13, 'covered_notes': [2], 'input': {'segments': []}}]}
        source['notes'].append({'status': 'estimated', 'lane': 3, 'target_seconds': 13, 'prediction_uncertainty_seconds': .01})
        _, evidence = draft(ucs.parse(TEMPLATE), source, {'song_start_seconds': 10, 'uncertainty_seconds': 0})
        self.assertEqual(evidence['summary']['placed_taps'], 1)
        self.assertEqual(evidence['summary']['placed_holds'], 0)
        self.assertEqual(len(evidence['unresolved']), 3)

    def test_registration_is_atomic_idempotent_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root/'repo'; output = root/'video/play/segment-001'
            output.mkdir(parents=True)
            initialize(repo, Provider())
            result = register(data(), output, repository=repo, song_start=10, client=Provider())
            self.assertEqual(result['status'], 'created')
            chart = Path(result['chart'])
            edited = chart.read_text().replace('X....', '....X', 1)
            chart.write_text(edited)
            metadata = chart.with_name('metadata.json')
            before = metadata.read_bytes()
            with patch.object(Provider, 'template', side_effect=AssertionError('Existing chart must not download')):
                again = register(data(), output, repository=repo, client=Provider())
            self.assertEqual(again['status'], 'existing')
            self.assertEqual(chart.read_text(), edited)
            self.assertEqual(metadata.read_bytes(), before)
            self.assertFalse(list(repo.rglob('*.mp3')))
            self.assertFalse(list(repo.rglob('*.build-*')))
            self.assertEqual(json.loads(before)['review_status'], 'unreviewed_draft')
            self.assertNotIn('path', json.loads(before)['source'])

    def test_identity_requires_unique_title_or_explicit_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = initialize(Path(temporary)/'repo', Provider())
            self.assertIsNone(resolve_code(repo, '카오스 어게인'))
            self.assertEqual(resolve_code(repo, 'Chaos Again'), 'CS349')
            remember_alias(repo, '카오스 어게인', 'CS349')
            self.assertEqual(resolve_code(repo, '카오스 어게인'), 'CS349')
            with self.assertRaises(ValueError):
                resolve_code(repo, 'Chaos Again', 'CS999')

    def test_optional_download_failure_retains_analysis_and_records_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = initialize(root/'repo', Provider()); output = root/'play'
            output.mkdir(); analysis = output/'analysis.json'; analysis.write_text('original')
            with patch.object(Provider, 'template', side_effect=OSError('network unavailable')):
                result = auto_register(data(), output, repository=repo, client=Provider())
            self.assertEqual(result['status'], 'pending')
            self.assertEqual(analysis.read_text(), 'original')
            self.assertEqual(json.loads((output/'chart-registration.json').read_text())['status'], 'pending')
            self.assertFalse((repo/'charts').exists())

    def test_catalogue_wrapped_cells_continue_across_page_break(self):
        pages = [[(43.3, 100, 'CS349'), (94.3, 100, '150~260'), (170.9, 100, '20'),
                  (247.4, 100, 'NAOKI'), (349.5, 100, 'CHAOS'), (450.4, 20, '1 / 2')],
                 [(247.4, 750, 'underground'), (349.5, 750, 'AGAIN'),
                  (43.3, 730, 'CS306'), (349.5, 730, 'Switronic')]]
        entries = catalogue_cells(pages)
        self.assertEqual(entries[0]['title'], 'CHAOS AGAIN')
        self.assertEqual(entries[0]['artist'], 'NAOKI underground')
        self.assertEqual(entries[1]['index'], 'CS306')
        with self.assertRaises(ValueError):
            catalogue_cells([pages[0], pages[0]])

    def test_zip_selects_members_without_extracting_paths_or_media(self):
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('../../CS349.ucs', TEMPLATE)
            archive.writestr('CS349.mp3', b'cached music')
            archive.writestr('../../unwanted', b'never extracted')
        document, music = read_archive(stream.getvalue(), 'CS349')
        self.assertEqual(document.mode, 'Single'); self.assertEqual(music, b'cached music')
        with self.assertRaises(ValueError):
            read_archive(b'<html>login</html>', 'CS349')
        with self.assertRaises(ValueError):
            parse_catalogue(b'<html>login</html>')
        with self.assertRaises(ValueError):
            read_archive(stream.getvalue(), '../CS349')
