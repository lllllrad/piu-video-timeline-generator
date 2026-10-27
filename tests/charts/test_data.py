from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from piu_timeline.charts import ucs
from piu_timeline.charts.data import draft, initialize, register, resolve_code, remember_alias, auto_register
from piu_timeline.charts.official import catalogue_cells, read_archive, parse_catalogue


TEMPLATE = ':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=2\n' + '.....\n'*16
CATALOGUE = {'schema': 1, 'songs': [{'index': 'CS349', 'title': 'CHAOS AGAIN', 'artist': 'NAOKI underground'}]}


class Provider:
    def catalogue(self):
        return CATALOGUE

    def template(self, code):
        return ucs.parse(TEMPLATE), Path('unused.mp3'), 'https://ucs.piugame.com/sample_download/zip.php?ucs_index='+code


def data():
    result = {'song': 'CHAOS AGAIN', 'chart': 'S21', 'segment_number': 1,
            'media': {'size_bytes': 123, 'mtime_ns': 456}, 'start_seconds': 10, 'end_seconds': 14,
            'layout': {'lanes': [{}]*5}, 'matches': [], 'combo_events': [], 'judgment_events': [],
            'notes': [{'status': 'estimated', 'lane': lane, 'target_seconds': target,
                       'prediction_uncertainty_seconds': .01} for lane, target in ((0, 10.5), (1, 11), (2, 11.5))]}
    prove_types(result)
    return result


def prove_types(source, holds=()):
    source['visual_channels']={'note_types':{'notes':[
        {'note':i,'observations':[{'kind':'hold' if i in holds else 'tap','reason':'synthetic_visible_shape',
                                  'playback_seconds':note['target_seconds']-.3,
                                  'source_pts_seconds':note['target_seconds']+4.7}]}
        for i,note in enumerate(source['notes'])]}}


class ChartDataTest(unittest.TestCase):
    def test_repeated_explicit_identity_preserves_existing_alias_proof(self):
        with tempfile.TemporaryDirectory()as temporary:
            repo=initialize(Path(temporary)/'repo',Provider())
            path=repo/'aliases.json'
            proof={'title':'Alternate title','index':'CS349','basis':'reference_audio_verified',
                   'alignment':{'song_start_seconds':12.3,'uncertainty_seconds':.01}}
            path.write_text(json.dumps({'alternatetitle':proof},indent=2)+'\n')
            before=path.read_bytes()
            remember_alias(repo,'Alternate title','CS349')
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(resolve_code(repo,'Alternate title'),'CS349')

    def test_chord_and_hold_transcription_do_not_read_input_or_judgment_associations(self):
        source=data()
        source['notes'][1]['target_seconds']=source['notes'][0]['target_seconds']
        source['hold_analysis']={'holds':[{'id':0,'lane':2,'start_range':[11.49,11.51],
            'end_range':[12.49,12.51],'start_censored':False,'end_censored':False,
            'head_note':2,'covered_notes':[2]}]}
        prove_types(source,holds={2})
        for field in ('matches','combo_events','judgment_events'):source.pop(field)
        original=deepcopy(source)
        document,evidence=draft(ucs.parse(TEMPLATE),source,{'song_start_seconds':10,'uncertainty_seconds':0})
        chord=next(row for section in document.sections for row in section.rows if row.startswith('XX'))
        self.assertEqual(chord,'XX...')
        self.assertEqual(evidence['summary']['placed_holds'],1)
        changed=deepcopy(source)
        for field in ('matches','combo_events','judgment_events','deferred_matches','miss_candidates'):
            changed[field]=[{'deliberately_unrelated_input_data':True}]
        changed['hold_analysis']['holds'][0]['input']={'press_range':[99,100],'segments':[{'unrelated':True}]}
        self.assertEqual(draft(ucs.parse(TEMPLATE),changed,{'song_start_seconds':10,'uncertainty_seconds':0}),
                         (document,evidence))
        self.assertEqual(source,original)

    def test_rebuild_preserves_reviewed_facts_and_refuses_a_regression_atomically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=initialize(root/'repo',Provider());output=root/'video/play/segment-001';output.mkdir(parents=True)
            result=register(data(),output,repository=repo,song_start=10,client=Provider())
            chart=Path(result['chart']);metadata_path=chart.with_name('metadata.json')
            metadata=json.loads(metadata_path.read_text())
            metadata['row_assertions']=[{'id':'reviewed-tap','start_seconds':.49,'end_seconds':.51,
                                        'cells':{'0':'X'},'reason':'Reviewed independent tap.'}]
            metadata_path.write_text(json.dumps(metadata));before=chart.read_bytes(),metadata_path.read_bytes()
            source=data();source['notes'][0]['target_seconds']=10.75;prove_types(source)
            with self.assertRaisesRegex(ValueError,'reviewed-tap failed'):
                register(source,output,repository=repo,song_start=10,client=Provider(),rebuild_draft=True)
            self.assertEqual((chart.read_bytes(),metadata_path.read_bytes()),before)

    def test_hold_caps_unknown_and_conflicting_types_never_become_ucs_taps(self):
        for kinds in (['hold'],['unknown'],['tap','hold'],[]):
            source=data()
            observations=source['visual_channels']['note_types']['notes'][0]['observations']
            observations[:]=[{'kind':kind,'reason':'synthetic_observed_shape',
                               'playback_seconds':10.1,'source_pts_seconds':15.1} for kind in kinds]
            original=deepcopy(source)
            document,evidence=draft(ucs.parse(TEMPLATE),source,{'song_start_seconds':10,'uncertainty_seconds':0})
            self.assertEqual(source,original)
            self.assertEqual([p['note'] for p in evidence['placements']],[1,2])
            self.assertEqual([p['note'] for p in evidence['unresolved']],[0])
            self.assertNotIn('X', ''.join(row[0] for section in document.sections for row in section.rows))
        source=data();source.pop('visual_channels')
        with self.assertRaisesRegex(ValueError,'No bounded notes'):
            draft(ucs.parse(TEMPLATE),source,{'song_start_seconds':10,'uncertainty_seconds':0})

    def test_complete_hold_does_not_override_a_contradictory_precontact_tap(self):
        source=data()
        source['hold_analysis']={'holds':[{'id':0,'lane':1,'start_range':[10.99,11.01],
            'end_range':[11.99,12.01],'start_censored':False,'end_censored':False,
            'head_note':1,'covered_notes':[1],'input':{'segments':[]}}]}
        # The original positive tap observation is before receptor contact.
        _,evidence=draft(ucs.parse(TEMPLATE),source,{'song_start_seconds':10,'uncertainty_seconds':0})
        self.assertEqual(evidence['summary']['placed_holds'],0)
        self.assertEqual(evidence['unresolved'],[{'note':1,'reason':'Contradictory tap and hold observations'}])

    def test_explicit_origin_survives_cache_reuse_only_for_same_recording(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = initialize(root/'repo', Provider()); output = root/'video/play/segment-001'
            output.mkdir(parents=True)
            auto_register(data(), output, repository=repo, song_start=10, client=Provider())
            reused = auto_register(data(), output, repository=repo, client=Provider())
            self.assertEqual(reused['alignment']['song_start_seconds'], 10)
            changed = data(); changed['media']['mtime_ns'] += 1
            replaced = auto_register(changed, output, repository=repo, client=Provider())
            self.assertNotIn('alignment', replaced)
            selected = auto_register(data(), output, repository=repo, song_start=10, revision='updated', client=Provider())
            persisted = auto_register(data(), output, repository=repo, client=Provider())
            self.assertEqual(persisted['revision'], 'updated')
            self.assertEqual(selected['chart'], persisted['chart'])

    def test_constant_tempo_template_can_extend_without_retiming_notes(self):
        source = data()
        source['end_seconds'] = 25
        source['notes'].append({'status': 'estimated', 'lane': 4, 'target_seconds': 22,
                                'prediction_uncertainty_seconds': .01})
        prove_types(source)
        alignment = {'song_start_seconds': 10, 'uncertainty_seconds': 0}
        _, incomplete = draft(ucs.parse(TEMPLATE), source, alignment)
        self.assertEqual(incomplete['summary']['unresolved_note_heads'], 1)
        doc, complete = draft(ucs.parse(TEMPLATE), source, alignment, extend_constant_tempo=True)
        self.assertEqual(complete['summary']['unresolved_note_heads'], 0)
        self.assertTrue(complete['timing_extension']['review_required'])
        self.assertEqual(complete['summary']['placed_taps'], 4)
        grid = list(doc.grid())
        placed=[(float(t),doc.sections[si].rows[ri])for si,ri,t in grid]
        self.assertIn((12.,'....X'),placed)
        self.assertEqual([p['song_seconds']for p in complete['placements']],[.5,1.,1.5,12.])
        self.assertEqual(complete['timing_extension']['original_last_row_seconds'],3.75)
        self.assertTrue(all(dict(s.directives)['Split']=='1'for s in doc.sections))

    def test_explicit_rebuild_preserves_backup_and_refuses_reviewed_or_edited_chart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = initialize(root/'repo', Provider()); output = root/'video/play/segment-001'
            output.mkdir(parents=True)
            result = register(data(), output, repository=repo, song_start=10, client=Provider())
            chart = Path(result['chart']); original = chart.read_bytes()
            metadata_path = chart.with_name('metadata.json')
            annotations = json.loads(metadata_path.read_text())
            annotations['regions'] = [{'id':'gimmick','start_seconds':1,'end_seconds':2,
                                       'processing':'exclude_timing','reason':'Nonlinear motion.'}]
            metadata_path.write_text(json.dumps(annotations))
            result = register(data(), output, repository=repo, song_start=10, client=Provider(), rebuild_draft=True)
            self.assertEqual(result['status'], 'rebuilt')
            self.assertEqual(json.loads(metadata_path.read_text())['regions'], annotations['regions'])
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
        prove_types(source,holds={1})
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
        prove_types(source,holds={2})
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
