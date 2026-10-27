"""Use real intermediate reads without promoting digit glitches or inventing states."""
import unittest

from piu_timeline.play.tracking import ComboTracker
from piu_timeline.play.counter_refinement import refine_events, refinement_constraints


def tracker(middle=40,confidence=.94,mode='independent_template',finish=1000.05):
    counter=ComboTracker()
    for t,value in [(999.90,39),(999.92,39),(999.95,39),(999.967,middle),
                    (1000.033,41),(finish,41)]:
        counter.update(t,value,confidence if value==middle else .97,mode,100+t)
    return counter


class CounterRefinementTest(unittest.TestCase):
    def test_long_parent_uses_only_independently_observed_bounded_substeps(self):
        for mode in ('independent_template','contrast_template'):
            with self.subTest(mode=mode):
                counter=ComboTracker()
                for t,value in [(0,5),(.017,5),(.033,5),(.116,6),(.149,7),(.166,7)]:
                    counter.update(t,value,.94,mode,10+t)
                self.assertEqual(counter.events[0]['status'],'excluded')
                result=refine_events(counter.events,counter.observations)
                self.assertEqual([(r['lower_seconds'],r['upper_seconds'])for r in result],[(.033,.116),(.116,.149)])
                self.assertTrue(all(r['status']=='candidate'and r['reason']is None for r in result))
                self.assertEqual(result[0]['aggregate_origin']['original_reason'],'combo_jump_or_observation_gap')
                self.assertEqual(result[1]['source_pts_seconds'],[10.116,10.149])
                # A real unobserved gap stays failed even if the total increment is known.
                reads=[{**r,'playback_seconds':.14}if r['value']==6 else r for r in counter.observations]
                self.assertEqual(refine_events(counter.events,reads),counter.events)

    def test_one_frame_independent_state_between_confirmed_neighbors_keeps_native_brackets(self):
        counter=tracker();events=refine_events(counter.events,counter.observations)
        self.assertEqual([(e['before'],e['after']) for e in events],[(39,40),(40,41)])
        self.assertEqual([(e['lower_seconds'],e['upper_seconds']) for e in events],
                         [(999.95,999.967),(999.967,1000.033)])
        self.assertEqual(events[0]['source_pts_seconds'],[1099.95,1099.967])
        self.assertEqual(sum(e['delta'] for e in events),counter.events[0]['delta'])
        self.assertEqual(events[0]['aggregate_origin']['intermediate_observations'][0]['confidence'],.94)

    def test_weak_contextual_missing_out_of_order_or_slow_confirmation_keeps_original_burst(self):
        for kind in ('weak','context','threshold','missing','backward','gap','slow','unobserved'):
            with self.subTest(kind=kind):
                counter=tracker(confidence=.89 if kind=='weak' else .94,
                                mode={'context':'temporal_template','threshold':'threshold_template'}.get(kind,'independent_template'),
                                middle=None if kind=='missing' else 40,
                                finish=1000.15 if kind=='slow' else 1000.05)
                if kind=='backward':counter.observations.insert(4,{'playback_seconds':999.98,'value':39})
                if kind=='gap':counter.events[0]['lower_seconds']=999.8
                if kind=='unobserved':counter.events[0].update(after=42,delta=3)
                self.assertEqual(refine_events(counter.events,counter.observations),counter.events)

    def test_legacy_calls_and_unconfirmed_last_values_cannot_supply_new_events(self):
        counter=ComboTracker()
        for t,value in [(0,39),(.01,39),(.02,40),(.03,41),(.04,41)]:counter.update(t,value)
        self.assertEqual(refine_events(counter.events,counter.observations),counter.events)
        counter=tracker();counter.events=[]
        self.assertEqual(refine_events(counter.events,counter.observations),[])

    def test_true_plus_ten_with_no_intermediate_pixels_remains_plus_ten(self):
        counter=ComboTracker()
        for t,value in [(0,20),(.01,20),(.02,30),(.03,30)]:
            counter.update(t,value,.99,'independent_template',10+t)
        result=refine_events(counter.events,counter.observations)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['delta'],10)


class RefinementOwnershipTest(unittest.TestCase):
    def test_added_counter_read_does_not_move_an_unrelated_unique_row_or_invent_constituents(self):
        counter=tracker();original=counter.events
        unrelated={'before':41,'after':42,'delta':1,'lower_seconds':1000.1,'upper_seconds':1000.12}
        original=original+[unrelated]
        notes=[{'status':'estimated'} for _ in range(4)]
        baseline=[{'combo_event':0,'note':0},{'combo_event':0,'note':1},{'combo_event':1,'note':2}]
        refined=refine_events(original,counter.observations)
        domains=refinement_constraints(notes,original,baseline,refined)
        self.assertEqual(domains,{0:{0,1},1:{0,1},2:{2}})
        # An originally unassigned burst cannot take an unrelated anchored row.
        domains=refinement_constraints(notes,original,baseline[2:],refined)
        self.assertEqual(domains[0],{0,1,3})
