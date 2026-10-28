"""Verify saved evidence crosses the Python/Node boundary without data loss."""
import unittest

from piu_timeline.derived import call


class DerivedTransportTest(unittest.TestCase):
    def references(self):
        return [{'note':i,'lane':i%2,'target_seconds':1+i/8,'offset':280+30*i,
                 'source_identity':{'mtime_ns':1780000000000000001,'caption':'한글🙂'*20000}}
                for i in range(5)]

    def test_multibyte_evidence_and_large_integer_provenance_survive_pipe_chunks(self):
        refs=self.references()
        model=call('coordinates.fit',refs,40)
        self.assertEqual(model['references'],refs)
        self.assertEqual(model['velocity_pixels_per_second'],240)
        self.assertEqual(model['maximum_reference_error_pixels'],0)

    def test_failed_fit_does_not_corrupt_the_next_request(self):
        with self.assertRaisesRegex(ValueError,'positive lane spacing'):
            call('coordinates.fit',[],0)
        self.assertEqual(call('coordinates.fit',self.references(),40)['velocity_pixels_per_second'],240)
