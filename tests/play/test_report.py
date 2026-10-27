from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import json

from piu_timeline.play.report import write_report


class ReportTest(unittest.TestCase):
    def test_processing_conflict_is_review_only_and_not_a_confirmed_grade(self):
        notes=[{'status':'estimated','lane':0,'target_seconds':10,'prediction_uncertainty_seconds':.01}]
        matches=[{'note':0,'target_seconds':10,'observation_lower_seconds':10.02,
                  'observation_upper_seconds':10.04,'judgment_label':'PERFECT','processing_conflict':True}]
        result=self.report_runtime(notes,matches)
        self.assertEqual(result['initialInputs'],[None])
        self.assertNotIn('PERFECT',' '.join(result['initialRows'][0]))
        self.assertIn('Conflicting refresh',result['initialRows'][0][4])
        self.assertEqual(result['defaultCandidateConnections'],0)
        self.assertEqual(result['optionalCandidateConnections'],1)


    def test_embedded_data_and_title_cannot_break_out_of_html(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.html'
            data = {'song': '</script><img src=x onerror=alert(1)>', 'chart': 'D22',
                    'media': {'path': str(Path(temporary) / 'source.mkv')}}
            write_report(data, path)
            text = path.read_text()
            self.assertNotIn('<img src=x', text)
            self.assertIn('\\u003c/script\\u003e', text)
            script = re.findall(r'<script>\s*(.*?)</script>', text, re.S)[0]
            if shutil.which('node'):
                js = Path(temporary) / 'report.js'
                js.write_text(script)
                subprocess.run(['node', '--check', str(js)], check=True, capture_output=True)


    def report_runtime(self, notes, matches, miss_candidates=(), lane_count=1, judgment_events=(), hold_analysis=None, chart_policy=None, visual_channels=None):
        data = {'song': 'Song', 'chart': 'S20', 'media': {'path': '/tmp/source.mkv'},
                'start_seconds': 8, 'end_seconds': 20, 'notes': notes, 'matches': matches,
                'display_delay_correction_ms': 0, 'bootstrap': {'ocr_images': 0, 'missing_digits': []},
                'frame_count': 100, 'combo_readable_fraction': 1, 'combo_events': [],
                'judgment_events': judgment_events, 'excluded_notes': {}, 'limitations': [],
                'miss_candidates': miss_candidates, 'hold_analysis': hold_analysis or {'holds': []},
                'layout': {'lanes': [{'name': str(i + 1), 'color': 'yellow'} for i in range(lane_count)]}}
        if visual_channels:
            data.update(visual_channels=visual_channels, analysis_height=200)
        if chart_policy:
            data['chart_policy'] = chart_policy
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.html'
            write_report(data, path)
            result = subprocess.run(['node', str(Path(__file__).with_name('report_runtime.cjs')), str(path)],
                                    check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_type_conflict_exposes_both_frame_links_without_changing_timing(self):
        notes=[{'status':'estimated','lane':0,'target_seconds':10,'prediction_uncertainty_seconds':.01,
                'type_status':'conflict','type_evidence':[
                    {'kind':'hold','playback_seconds':9.8,'source_pts_seconds':49.8,'reason':'visible_body'},
                    {'kind':'tap','playback_seconds':9.9,'source_pts_seconds':49.9,'reason':'isolated_cap'}]}]
        result=self.report_runtime(notes,[])
        self.assertEqual(result['typePreview'],{'status':'conflict','seek':9.8})
        self.assertEqual(result['initialInputs'],[None])

    def test_region_policy_is_rendered_without_input_markers_or_erasing_notes(self):
        notes = [{'status':'estimated','lane':0,'target_seconds':10,'prediction_uncertainty_seconds':.01}]
        matches = [{'note':0,'target_seconds':10,'observation_lower_seconds':10.02,'observation_upper_seconds':10.04}]
        policy = {'status':'applied','regions':[{'id':'scroll','start_seconds':0,'end_seconds':4,
                    'playback_start_seconds':8,'playback_end_seconds':12,'processing':'exclude_timing',
                    'check_exceptions':['timing_evidence'],'reason':'Nonlinear motion.'}]}
        result = self.report_runtime(notes, matches, chart_policy=policy)
        self.assertEqual(result['initialInputs'], [None])
        self.assertTrue(all(marker['color'] != '#ff70dd' for marker in result['initialMarkers']))
        self.assertIn('Timing excluded by chart policy', result['initialRows'][0][4])

    def test_comparison_includes_both_uncertainties_and_latency_correction(self):
        notes = [{'status': 'estimated', 'lane': 0, 'target_seconds': 10,
                  'prediction_uncertainty_seconds': .01},
                 {'status': 'estimated', 'lane': 0, 'target_seconds': 11,
                  'prediction_uncertainty_seconds': .02}]
        matches = [{'note': 0, 'target_seconds': 10, 'combo_event': None, 'judgment_event': 0,
                    'judgment_label': 'PERFECT', 'observation_lower_seconds': 10.02,
                    'observation_upper_seconds': 10.04, 'raw_offset_lower_ms': 20, 'raw_offset_upper_ms': 40}]
        result = self.report_runtime(notes, matches, [{'note': 1, 'judgment_event': 1}])
        self.assertEqual(result['targetRanges'], [[9.99, 10.01], [10.98, 11.02]])
        for actual, expected in zip(result['initialDifferences'][0], (10, 50)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(result['correctedDifferences'][0], (-20, 20)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(result['correctedInputs'][0], (9.99, 10.01)):
            self.assertAlmostEqual(actual, expected)
        self.assertIn('Later than target range', result['initialRows'][0][3])
        self.assertIn('Overlaps target range', result['correctedRows'][0][3])
        # The corrected intervals coincide in time, but both colored markers
        # must survive on opposite sides of the fixed square.
        marks = {mark['color']: mark['args'] for mark in result['correctedMarkers']}
        self.assertEqual(set(marks), {'#b6ff59', '#ff70dd'})
        self.assertAlmostEqual(marks['#b6ff59'][1], marks['#ff70dd'][1])
        self.assertLess(marks['#b6ff59'][0], result['verticalNotes'][0]['x'])
        self.assertGreater(marks['#ff70dd'][0], result['verticalNotes'][0]['x'])
        self.assertIsNone(result['initialInputs'][1])
        self.assertIsNone(result['correctedDifferences'][1])
        self.assertEqual(result['correctedRows'][1][2], 'Unconfirmed')
        self.assertIn('Possible MISS', result['correctedRows'][1][4])
        self.assertIn('Input: Unconfirmed', result['details'][1][0])
        self.assertEqual(result['correctedRows'][0][1], result['initialRows'][0][1])

    def test_shared_aggregate_bracket_is_preserved_and_missing_motion_excluded(self):
        notes = [{'status': 'estimated', 'lane': 0, 'target_seconds': target,
                  'prediction_uncertainty_seconds': .01} for target in (10, 10.03)]
        notes.append({'status': 'excluded', 'lane': 0, 'target_seconds': None, 'points': [[12, .3]]})
        matches = [{'note': i, 'target_seconds': note['target_seconds'], 'combo_event': None,
                    'judgment_event': 0, 'aggregate_row_count': 2, 'observation_lower_seconds': 9.98,
                    'observation_upper_seconds': 10.04, 'raw_offset_lower_ms': -20, 'raw_offset_upper_ms': 40}
                   for i, note in enumerate(notes[:2])]
        result = self.report_runtime(notes, matches)
        self.assertEqual(len(result['initialRows']), 2)
        self.assertEqual(result['initialInputs'], [[9.98, 10.04]] * 2)
        self.assertTrue(all('aggregate row bracket' in row[4] for row in result['initialRows']))
        self.assertIn('Aggregate refresh bracket', ' '.join(result['details'][0]))

    def test_comparison_legacy_combo_bracket_early_input_and_no_matches(self):
        note = {'status': 'estimated', 'lane': 0, 'target_seconds': 10,
                'prediction_uncertainty_seconds': .01}
        match = {'note': 0, 'target_seconds': 10, 'combo_event': None,
                 'combo_lower_seconds': 9.95, 'combo_upper_seconds': 9.97,
                 'raw_offset_lower_ms': -50, 'raw_offset_upper_ms': -30}
        result = self.report_runtime([note], [match])
        self.assertIn('Earlier than target range', result['initialRows'][0][3])
        self.assertEqual(result['initialInputs'], [[9.95, 9.97]])
        match['judgment_label'] = 'MISS'
        result = self.report_runtime([note], [match])
        self.assertIsNone(result['initialInputs'][0])
        result = self.report_runtime([note], [])
        self.assertEqual(result['initialInputs'], [None])
        self.assertIn('Input unknown', result['initialRows'][0][4])
        self.assertEqual(self.report_runtime([], [])['initialRows'], [])

    def test_vertical_chart_orders_lanes_and_time_and_aligns_chords(self):
        for lane_count in (5, 10):
            with self.subTest(lanes=lane_count):
                notes = [{'status': 'estimated', 'lane': lane, 'target_seconds': target,
                          'prediction_uncertainty_seconds': .01}
                         for lane, target in ((0, 10), (lane_count - 1, 10), (1, 10.4))]
                result = self.report_runtime(notes, [], lane_count=lane_count)
                first, chord, later = result['verticalNotes']
                self.assertLess(first['x'], later['x'])
                self.assertLess(later['x'], chord['x'])
                self.assertEqual(first['y'], chord['y'])
                self.assertLess(first['y'], later['y'])
                self.assertEqual(result['initialInputs'], [None, None, None])

    def test_neighbor_frame_alternatives_are_shown_as_separate_ranges(self):
        notes = [{'status': 'estimated', 'lane': 0, 'target_seconds': 10,
                  'prediction_uncertainty_seconds': .01}]
        events = [{'label': 'PERFECT', 'lower_seconds': lo, 'upper_seconds': hi,
                   'trigger': 'animation_restart', 'status': 'excluded', 'reason': 'ambiguous'}
                  for lo, hi in ((10.12, 10.14), (10.2, 10.23))]
        result = self.report_runtime(notes, [], judgment_events=events)
        self.assertIn(' ∪ ', result['initialRows'][0][2])
        self.assertIn(' ∪ ', result['initialRows'][0][3])
        self.assertIn('Possible refresh ranges', result['initialRows'][0][4])
        self.assertIn('association is unresolved', ' '.join(result['details'][0]))
        self.assertEqual(result['defaultCandidateConnections'], 0)
        self.assertGreater(result['optionalCandidateConnections'], 0)
        self.assertAlmostEqual(result['correctedInputs'][0][0], 10.09)

    def test_individual_report_includes_side_by_side_layout_css(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.html'
            write_report({'song': 'Song', 'chart': 'D20', 'media': {'path': '/tmp/source.mkv'}}, path)
            report = path.read_text()
        stylesheet = re.search(r'<style>(.*?)</style>', report, re.S)[1]
        # Both the wrapper and its desktop grid rules must ship in the report,
        # rather than only in the separate report index.
        self.assertIn('class="playback-grid"', report)
        layout = re.search(r'\.playback-grid\s*\{([^}]+)\}', stylesheet)[1]
        self.assertRegex(layout, r'display\s*:\s*grid')
        columns = re.search(r'grid-template-columns\s*:\s*([^;}]+)', layout)[1]
        self.assertEqual(len(re.findall(r'minmax\([^)]*\)|[\w.]+fr', columns)), 2)
        self.assertRegex(stylesheet, r'\.video-panel\s*\{[^}]*position:sticky')

    def test_long_note_chart_and_input_are_sustained_spans_not_tap_offsets(self):
        notes = [{'status': 'estimated', 'lane': 0, 'target_seconds': target,
                  'prediction_uncertainty_seconds': .01, 'points': []} for target in (10.01, 11.01)]
        hold = {'id': 0, 'lane': 0, 'start_range': [10, 10.02], 'end_range': [11, 11.02],
                'start_censored': False, 'end_censored': False, 'head_note': 0,
                'last_body_seconds': 10.99, 'covered_notes': [0, 1],
                'input': {'segments': [{'lower_seconds': 10.03, 'upper_seconds': 10.3}],
                          'recognition_envelope': [10.03, 10.3], 'press_range': None, 'release_range': None}}
        result = self.report_runtime(notes, [], hold_analysis={'holds': [hold]})
        self.assertEqual(len(result['initialRows']), 1)
        self.assertIn('HOLD', result['initialRows'][0][0])
        self.assertEqual(result['initialRows'][0][3], 'Sustained state; no repeated presses')
        self.assertIn('physical release unknown', result['initialRows'][0][4])
        self.assertIn('Holding before the visual start is sufficient', ' '.join(result['details'][0]))
        hold.update(start_range=[8, 10.02], start_censored=True, head_note=None)
        result = self.report_runtime(notes, [], hold_analysis={'holds': [hold]})
        self.assertIn('already visible / uncertain', result['initialRows'][0][1])

    def test_four_channel_view_shows_raw_values_seeks_source_frames_and_retains_dom(self):
        notes = [{'status':'estimated','lane':0,'target_seconds':t,'prediction_uncertainty_seconds':.01}
                 for t in (10,11)]
        channels = {
            'timeline': {'frames':[[9.98,99.98],[10,100],[10.02,100.02],[11,101]]},
            'popup': {'combo_events':[], 'judgment_events':[],
                      'observations':[[3,.9,None,0,True],[4,.95,'GREAT',.91,False],
                                      [4,.95,'GREAT',.92,False],[5,.96,'PERFECT',.94,False]]},
            'receptors': {'onsets':1, 'unknown_lane_frames':1, 'events':[],
                          'observations':[[[False],[.1],False],[[None],[.65],True],
                                          [[True],[.9],False],[[False],[.05],False]]},
            'motion': {'detections':2, 'tracks':[{},{}],
                       'hold_risk':{'frames':[{'playback_seconds':10,'source_pts_seconds':100,'causes':[
                           {'lane':1,'vertical_range_pixels':[30,65],'state':'approaching','owner_hold':7},
                           {'lane':2,'vertical_range_pixels':[10,50],'state':'unresolved'}]}]},
                       'observations':[[[0,.5,.4,.88]],[],[],[[0,.5,.3,.9]]]},
            'processing': {'pixel_coordinates':{'width':325,'height':100},
                           'body_observations':[[[0,25,40,True,False,True,.9]],[],[],[]],
                           'counts':{'disappeared_near_receptor':1,'unresolved':1},
                           'notes':[{'note':0,'id':'processing:0','status':'disappeared_near_receptor',
                                     'reason':'verified_head_then_clear_absence','range':[9.98,10.02],
                                     'template_evidence':{'poses':[{'source_pts_seconds':99.5}]},
                                     'samples':[{'time':9.98,'state':'present','score':.9,'template_pose':0,'template_vertical_offset_pixels':1},
                                                {'time':10,'state':'unknown','score':None,'unknown_reason':'white_effect'},
                                                {'time':10.02,'state':'absent','score':.01}]},
                                    {'note':1,'id':'processing:1','status':'unresolved',
                                     'reason':'insufficient_clear_approach','samples':[]}]}}
        result = self.report_runtime(notes, [], visual_channels=channels)['evidencePreview']
        self.assertIn('3 / 0.90',result['rows'][0])
        self.assertIn('GREAT / 0.91',result['rows'][1])
        self.assertIn('unknown (common flash) / 0.65',result['rows'][1])
        self.assertIn('lane 2 proximity 30…65 px / approaching / hold 7',result['rows'][1])
        self.assertIn('lane 3 proximity 10…50 px / unresolved / unowned',result['rows'][1])
        self.assertIn('80.0',result['rows'][0])
        self.assertIn('body 50.0…80.0 px / tail clipped',result['rows'][0])
        self.assertIn('shape 0 / reference PTS 99.500000',result['rows'][0])
        self.assertIn('vertical offset 1 feature px',result['rows'][0])
        self.assertIn('unknown / ? / white_effect',result['rows'][1])
        self.assertEqual(result['seekTime'],10)
        self.assertIn('insufficient_clear_approach',result['secondNoteSummary'])
