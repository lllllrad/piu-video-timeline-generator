"""Verify saved evidence crosses the Python/Node boundary without data loss."""
import unittest

from piu_timeline.derived import call


class DerivedTransportTest(unittest.TestCase):
    def references(self):
        return [{'status':'excluded','delta':1,'lower_seconds':1+i/8,'upper_seconds':1.01+i/8,
                 'source_identity':{'mtime_ns':1780000000000000001,'caption':'한글🙂'*20000}}
                for i in range(5)]

    def test_multibyte_evidence_and_large_integer_provenance_survive_pipe_chunks(self):
        refs=self.references()
        result=call('stageAssociations.counters',self.request(refs))['data']
        self.assertEqual(result['combo_events'],refs)
        self.assertEqual(result['matches'],[])

    def request(self,events):
        return {'schema':1,'notes':[],'events':events,'display_delay_seconds':0,'unsupported_intervals':[]}

    def test_failed_request_does_not_corrupt_the_next_response(self):
        with self.assertRaisesRegex(ValueError,'Invalid counter association input'):
            call('stageAssociations.counters',{'schema':99})
        refs=self.references()
        self.assertEqual(call('stageAssociations.counters',self.request(refs))['data']['combo_events'],refs)
