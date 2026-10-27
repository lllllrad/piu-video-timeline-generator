"""Derived holds preserve required presses and original bounded evidence."""
from copy import deepcopy
import unittest

from piu_timeline.charts.hold_simplification import simplify
from tests.charts.test_transcription import template


def fixtures(gaps=(.04,.04)):
    observed=[];edges={};notes=[];start=.25
    for i,gap in enumerate((0,*gaps)):
        if i:start+=gap
        end=start+.25
        observed.append({'note':i,'lane':0,'kind':'hold',
                         'observed_target_range':[start-.002,start+.002],
                         'observed_end_range':[end-.002,end+.002]})
        edges[i,'head']=[start-.002,start+.002];edges[i,'tail']=[end-.002,end+.002]
        notes.append({'lane':0,'target_seconds':start,'prediction_uncertainty_seconds':.002})
        start=end
    return observed,edges,notes


class HoldSimplificationTest(unittest.TestCase):
    def test_continuous_held_state_can_support_a_larger_short_gap_but_never_swallow_a_tap(self):
        observed,edges,notes=fixtures(gaps=(.2,))
        run={'lane':0,'lit':True,'frames':30,'start_seconds':10.4,'end_seconds':10.8,
             'first_source_pts_seconds':30.4,'last_source_pts_seconds':30.8}
        # Endpoint coordinates are song-relative; input observations use original playback time.
        result,_,proof=simplify(template(),observed,edges,notes,10,[run])
        self.assertEqual(len(result),1)
        gap=proof['merges'][0]['bridged_gaps'][0]
        self.assertEqual(gap['basis'],'continuous_held_state')
        self.assertEqual(gap['held_state_evidence']['source_pts_range'],[30.4,30.8])
        for change in ({'lane':1},{'lit':False},{'lit':None},{'start_seconds':10.51},{'end_seconds':10.69},{'frames':1}):
            self.assertEqual(len(simplify(template(),observed,edges,notes,10,[{**run,**change}])[0]),2)
        notes.append({'lane':0,'target_seconds':10.6,'prediction_uncertainty_seconds':.01})
        self.assertEqual(len(simplify(template(),observed,edges,notes,10,[run])[0]),2)

    def test_proven_hold_components_do_not_block_merging_but_pending_cap_roles_do(self):
        observed,edges,notes=fixtures(gaps=(.04,))
        component={'lane':0,'target_seconds':.5,'prediction_uncertainty_seconds':.01,
                   'note_type':'hold_component','reason':'long_note_body_or_tail'}
        notes.append(component)
        self.assertEqual(len(simplify(template(),observed,edges,notes,0)[0]),1)
        component['reason']='observed_hold_tail_pending_geometry'
        self.assertEqual(len(simplify(template(),observed,edges,notes,0)[0]),2)

    def test_chain_merges_without_mutating_source_and_retains_every_interval(self):
        observed,edges,notes=fixtures();before=deepcopy((observed,edges,notes))
        result,new_edges,proof=simplify(template(),observed,edges,notes,0)
        self.assertEqual((observed,edges,notes),before)
        self.assertEqual(len(result),1)
        self.assertEqual(new_edges,{(0,'head'):edges[0,'head'],(0,'tail'):edges[2,'tail']})
        self.assertEqual([o['note']for o in result[0]['source_hold_intervals']],[0,1,2])
        self.assertEqual(len(proof['merges'][0]['bridged_gaps']),2)
        self.assertEqual(proof['policy']['hold_tick_equivalence'],'unverified')

    def test_tap_or_unresolved_head_blocks_bridge_even_if_not_exportable(self):
        for target in (.52,None):
            observed,edges,notes=fixtures(gaps=(.04,))
            notes.append({'lane':0,'target_seconds':target,'prediction_uncertainty_seconds':.01})
            result,new_edges,proof=simplify(template(),observed,edges,notes,0)
            self.assertEqual(len(result),2);self.assertEqual(new_edges,edges)
            self.assertFalse(proof['merges'])

    def test_long_gap_and_contained_duplicate_are_not_simplified(self):
        observed,edges,notes=fixtures(gaps=(.2,))
        self.assertEqual(len(simplify(template(),observed,edges,notes,0)[0]),2)
        edges[1,'head']=[.3,.304];edges[1,'tail']=[.4,.404]
        self.assertEqual(len(simplify(template(),observed,edges,notes,0)[0]),2)

    def test_fast_tempo_tightens_gap_bound(self):
        observed,edges,notes=fixtures(gaps=(.08,))
        self.assertEqual(len(simplify(template(),observed,edges,notes,0)[0]),1)
        fast=template();fast.sections[0].directives=[(k,'240'if k=='BPM'else v)for k,v in fast.sections[0].directives]
        self.assertEqual(len(simplify(fast,observed,edges,notes,0)[0]),2)
