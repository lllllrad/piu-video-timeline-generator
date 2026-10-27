"""Common phase calibration is consumed once, with its matching reference."""
from copy import deepcopy
from hashlib import sha256
import unittest

from piu_timeline.charts.phase import transcription_alignment
from piu_timeline.charts import ucs
from piu_timeline.charts.data import draft
from tests.charts.test_data import data,prove_types


def fixture():
    template=ucs.parse(':Format=1\n:Mode=Single\n:BPM=155\n:Delay=0\n:Beat=4\n:Split=1\n'+'.....\n'*4)
    alignment={'song_start_seconds':10,'uncertainty_seconds':.01,'rate':1}
    source=data();source['notes']=source['notes'][:2]
    step=60/(155*12)
    for note,row in zip(source['notes'],(1,4)):
        note.update(target_seconds=10+.007+row*step,prediction_uncertainty_seconds=.0187)
    prove_types(source)
    source['beat_timing']={'status':'failed','song_phase_correction_seconds':.007,
        'song_phase_range':[.0065,.0075],'groups':[{'status':'restored'}],
        'contract':{'reference':{'status':'available','sha256':sha256(template.text().encode()).hexdigest(),
            'song_start_seconds':10,'alignment_uncertainty_seconds':.01}}}
    return template,source,alignment


class TranscriptionPhaseTest(unittest.TestCase):
    def test_matching_phase_preserves_exact_subdivision_without_readding_audio_error(self):
        template,source,alignment=fixture();original=deepcopy((source,alignment))
        document,evidence=draft(template,source,alignment)
        self.assertEqual((source,alignment),original)
        self.assertEqual(evidence['summary']['placed_taps'],2)
        self.assertEqual(evidence['unresolved'],[])
        self.assertEqual(evidence['transcription']['measures'][0]['split'],12)
        for placement,row in zip(evidence['placements'],(1,4)):
            self.assertAlmostEqual(placement['song_seconds'],row*60/(155*12))
        proof=evidence['transcription_alignment']
        self.assertAlmostEqual(proof['song_start_seconds'],10.007)
        self.assertAlmostEqual(proof['uncertainty_seconds'],.0005)
        self.assertEqual(proof['phase_range'],[.0065,.0075])
        self.assertEqual(ucs.parse(document.text()),document)

    def test_changed_timing_origin_uncertainty_or_rate_cannot_reuse_stale_phase(self):
        template,source,alignment=fixture()
        for change in ({'song_start_seconds':10.002},{'uncertainty_seconds':0},{'rate':1.001}):
            selected,proof=transcription_alignment(template,source,{**alignment,**change})
            self.assertEqual(selected,{**alignment,**change})
            self.assertEqual(proof['method'],'audio_alignment')
            self.assertIn('unused_phase_reason',proof)
        source['beat_timing']['contract']['reference']['sha256']='unrelated'
        self.assertEqual(transcription_alignment(template,source,alignment)[0],alignment)

    def test_invalid_or_unsupported_phase_fails_explicitly(self):
        template,source,alignment=fixture()
        for change in ({'song_phase_range':[.008,.009]},{'song_phase_range':[-.02,.02]},
                       {'song_phase_correction_seconds':float('nan')},{'groups':[]}):
            with self.assertRaisesRegex(ValueError,'Invalid bounded common song phase'):
                transcription_alignment(template,{**source,'beat_timing':{**source['beat_timing'],**change}},alignment)

    def test_missing_phase_keeps_audio_alignment(self):
        template,source,alignment=fixture();source.pop('beat_timing')
        selected,proof=transcription_alignment(template,source,alignment)
        self.assertEqual(selected,alignment);self.assertEqual(proof['method'],'audio_alignment')
