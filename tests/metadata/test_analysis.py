"""Offline automatic orchestration and decoded-boundary tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
from piu_timeline.metadata import analysis as auto, profiles as hud_profiles
from piu_timeline import media


class AutoTest(unittest.TestCase):
    def test_ocr_backend_change_preserves_acquisition_and_invalidates_only_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);segment=root/'evidence/segment-001';segment.mkdir(parents=True)
            stats=root/'evidence/stats-001';stats.mkdir()
            image=segment/'frame.png';image.write_bytes(b'unchanged pixels')
            acquisition={'file':str(image),'source_pts_seconds':8.25,'playback_seconds':3.25,
                         'requested_seconds':3.2,'roi':[0,0,100,100],'window':'result'}
            (segment/'ocr.json').write_text(json.dumps([{**acquisition,'ocr':[{'text':'old'}],
                                                       'scene':'result','focused_ocr':[{'text':'old'}]}]))
            (segment/'stage.json').write_text(json.dumps({**acquisition,'recognized':{'value':1},'ocr':[]}))
            plan=segment/'result-transitions.json';plan.write_text('[3.2, 4.0]')
            (stats/'frames.json').write_text('[]');crop=stats/'crop.png';crop.write_bytes(b'old input crop')
            auto.reset_ocr_evidence(root)
            self.assertEqual(json.loads((segment/'ocr.json').read_text()),[acquisition])
            self.assertEqual(json.loads((segment/'stage.json').read_text()),acquisition)
            self.assertEqual(plan.read_text(),'[3.2, 4.0]')
            self.assertEqual(image.read_bytes(),b'unchanged pixels')
            self.assertEqual(crop.read_bytes(),b'old input crop')
            self.assertFalse((stats/'frames.json').exists())

    def setUp(self):
        visual = patch.object(auto.SceneRouter, "signatures", return_value=None)
        visual.start()
        self.addCleanup(visual.stop)
        probe = patch.object(auto, "screen_lines", side_effect=lambda path, width, height:
                             auto.ocr_images([path])[0]["lines"])
        probe.start()
        self.addCleanup(probe.stop)
        for name in ("transition_samples", "focused_names"):
            mocked = patch.object(auto, name, return_value=[])
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_reference_uses_english_hud_and_preserves_decoded_time(self):
        frame = {"file": "reference.png", "playback_seconds": 30.04}
        # The multilingual model reads this label as STAG드 on Linux.
        def recognize(paths, english=False):
            return [{"lines": [{"text": "STAGE" if english else "STAG드",
                                "box": [.14, .01, .05, .02]}]}]
        with patch.object(hud_profiles, "capture_game", return_value=frame), \
                patch.object(hud_profiles, "ocr_images", side_effect=recognize):
            seconds, hud, evidence = auto.find_reference(
                {"duration_seconds": 100}, (10, 20, 1300, 730), Path("unused"))
        self.assertEqual(seconds, 30.04)
        self.assertEqual(hud, (190, 25, 69, 19))
        self.assertEqual(evidence["ocr"]["lines"][0]["text"], "STAGE")

    def test_transition_first_ocr_keeps_late_summary_without_dense_result_scan(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            def capture(record, path, seconds, roi):
                paths[str(path)] = seconds
                return {"file": str(path), "source_pts_seconds": seconds,
                        "requested_seconds": seconds, "playback_seconds": seconds}
            def recognize(files):
                return [{"lines": ([line("PLAY RESULT", .4, .1)] if paths[p] >= 230
                                  else [line("SCORE", .8, .35), line("PERFECT", .5, .4)]
                                  if paths[p] > 200 else [])} for p in files]
            def focus(path, scene, width, height):
                if scene == "summary":
                    return [line("1ST", .48, .18), line("Played song", .4, .22, .2),
                            line("DOUBLE", .72, .17), line("20", .72, .20)]
                return [line("Played song", .4, .16, .2), line("DOUBLE", .65, .28),
                        line("20", .65, .32)]
            with patch.object(auto, "transition_samples", side_effect=[[90.25, 90.85],
                                                                      [205.25, 205.85, 230.25, 230.85]]) as transitions, \
                    patch.object(auto, "capture_game", side_effect=capture), \
                    patch.object(auto, "ocr_images", side_effect=recognize), \
                    patch.object(auto, "focused_lines", side_effect=focus):
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 300}, (0, 0, 1300, 730), 100, 200,
                    Path(temporary), stage=1, previous_end=80, next_start=270)
            observations = json.loads(Path(evidence).read_text())
            self.assertEqual(labels, {"song": "Played song", "chart": "D20"})
            results = [o for o in observations if o["window"] == "result"]
            self.assertLessEqual(len(results), 12)
            self.assertNotIn(208, [o["requested_seconds"] for o in results])
            self.assertGreaterEqual(sum(o["scene"] == "summary" for o in results), 2)
            self.assertEqual(transitions.call_count, 2)
            self.assertTrue(all(o["source_pts_seconds"] == o["requested_seconds"] for o in observations))

    def test_unresolved_transition_samples_fall_back_to_dense_metadata_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            with patch.object(auto, "transition_samples", side_effect=[[90.25, 90.85], [205.25, 205.85]]), \
                    patch.object(auto, "capture_game", side_effect=capture) as capture_mock, \
                    patch.object(auto, "ocr_images", side_effect=lambda paths: [{"lines": []} for _ in paths]):
                labels, _, _ = auto.recognize_segment(
                    {"duration_seconds": 300}, (0, 0, 1300, 730), 100, 200,
                    Path(temporary), previous_end=80, next_start=270)
            self.assertEqual(labels, {"song": None, "chart": None})
            self.assertIn(208, [call.args[2] for call in capture_mock.call_args_list])

    def test_dense_fallback_corroborates_a_previously_missed_short_result(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            def capture(record, path, seconds, roi):
                paths[str(path)] = seconds
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            def recognize(files):
                return [{"lines": [line("SCORE", .8, .35), line("PERFECT", .5, .4)]
                         if 207.5 < paths[p] < 208.5 else []} for p in files]
            focused = [line("Short song", .4, .16, .2), line("DOUBLE", .65, .28), line("20", .65, .32)]
            with patch.object(auto, "transition_samples", side_effect=[[], [205.25, 205.85]]), \
                    patch.object(auto, "capture_game", side_effect=capture), \
                    patch.object(auto, "ocr_images", side_effect=recognize), \
                    patch.object(auto, "focused_lines", return_value=focused):
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 300}, (0, 0, 1300, 730), 100, 200,
                    Path(temporary), previous_end=80, next_start=270)
            self.assertEqual(labels, {"song": "Short song", "chart": "D20"})
            observations = json.loads(Path(evidence).read_text())
            self.assertGreaterEqual(sum(o["scene"] == "result" for o in observations), 2)

    def test_unknown_screens_have_a_bounded_full_frame_ocr_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            with patch.object(auto, "capture_game", side_effect=capture), \
                    patch.object(auto, "screen_lines", return_value=[]), \
                    patch.object(auto, "ocr_images", side_effect=lambda paths: [{"lines": []} for _ in paths]) as full:
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 300}, (0, 0, 1300, 730), 100, 200,
                    Path(temporary), previous_end=80, next_start=270)
            self.assertEqual(labels, {"song": None, "chart": None})
            self.assertGreater(len(json.loads(Path(evidence).read_text())), 20)
            self.assertEqual(full.call_count, 4)

    def test_repeated_result_frames_have_a_bounded_title_chart_read_budget(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            def capture(record, path, seconds, roi):
                paths[str(path)] = seconds
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            def probe(path, width, height):
                return [line("SCORE", .8, .35), line("PERFECT", .5, .4)] if paths[path] > 200 else []
            focused = [line("Repeated song", .4, .16, .2), line("DOUBLE", .65, .28), line("20", .65, .32)]
            with patch.object(auto, "capture_game", side_effect=capture), \
                    patch.object(auto, "screen_lines", side_effect=probe), \
                    patch.object(auto, "ocr_images", side_effect=lambda paths: [{"lines": []} for _ in paths]), \
                    patch.object(auto, "focused_lines", return_value=focused) as focus:
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 300}, (0, 0, 1300, 730), 100, 200,
                    Path(temporary), previous_end=80, next_start=270)
            self.assertEqual(labels, {"song": "Repeated song", "chart": "D20"})
            self.assertEqual(focus.call_count, 2)
            self.assertGreater(sum(o["scene"] == "result" for o in json.loads(Path(evidence).read_text())), 20)


    def test_sampling_does_not_cross_neighbor_intervals(self):
        with tempfile.TemporaryDirectory() as temporary:
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            with patch.object(auto, "capture_game", side_effect=capture) as capture_mock, \
                 patch.object(auto, "ocr_images", side_effect=lambda paths: [{"lines": []} for _ in paths]), \
                 patch.object(auto, "focused_lines") as focus:
                auto.recognize_segment({"duration_seconds": 100}, (0, 0, 1300, 730),
                                       10, 20, Path(temporary), previous_end=7, next_start=25)
            self.assertTrue(all(7 < call.args[2] < 25 for call in capture_mock.call_args_list))
            self.assertIn(21.25, [call.args[2] for call in capture_mock.call_args_list])
            focus.assert_not_called()

    def test_short_result_between_old_offsets_is_recovered(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            def ocr(paths):
                return [{"lines": [line("SCORE", .8, .35), line("PERFECT", .5, .4)]
                         if Path(path).stem in {"adaptive-result-21.250", "adaptive-result-22.000"}
                         else []} for path in paths]
            with patch.object(auto, "capture_game", side_effect=capture), \
                 patch.object(auto, "ocr_images", side_effect=ocr), \
                 patch.object(auto, "focused_lines", return_value=[line("Short result", .4, .16, .2)]):
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 100}, (0, 0, 1300, 730), 10, 20, Path(temporary),
                    previous_end=7, next_start=25)
            self.assertEqual(labels["song"], "Short result")
            self.assertEqual(sum(o["scene"] == "result" for o in json.loads(Path(evidence).read_text())), 2)

    def test_retained_acquisition_adds_late_summary_samples(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            old = [{"file": str(directory / f"result-{i}.png"), "requested_seconds": t,
                    "source_pts_seconds": t, "window": "result", "phase": "result", "scene": "result",
                    "ocr": [line("SCORE", .8, .35), line("PERFECT", .5, .4)],
                    "focused_ocr": [line("Wrong background", .4, .16, .2)], "eligible_screen": True}
                   for i, t in enumerate((23, 25))]
            (directory / "ocr.json").write_text(json.dumps(old))
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            def ocr(paths):
                return [{"lines": [line("PLAY RESULT", .4, .1)]
                         if Path(path).stem in {"result-15", "result-16"} else []} for path in paths]
            row = [line("1ST", .48, .18), line("Played song", .4, .22, .2),
                   line("DOUBLE", .72, .17), line("20", .72, .20)]
            with patch.object(auto, "capture_game", side_effect=capture) as captured, \
                 patch.object(auto, "ocr_images", side_effect=ocr), \
                 patch.object(auto, "focused_lines", return_value=row):
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 100}, (0, 0, 1300, 730), 10, 20, directory,
                    stage=1, previous_end=7, next_start=90)
            self.assertEqual(labels, {"song": "Played song", "chart": "D20"})
            times = [call.args[2] for call in captured.call_args_list]
            self.assertNotIn(23, times)
            self.assertNotIn(25, times)
            self.assertIn(60, times)
            self.assertTrue(Path(evidence).is_file())

    def test_single_short_summary_is_corroborated_by_nearby_frames(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            paths = {}
            def capture(record, path, seconds, roi):
                paths[str(path)] = seconds
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            def ocr(files):
                return [{"lines": [line("PLAY RESULT", .4, .1)] if 26.5 < paths[p] < 27.5 else []} for p in files]
            title = [line("1ST", .48, .18), line("Short summary", .4, .22, .2)]
            with patch.object(auto, "capture_game", side_effect=capture), \
                 patch.object(auto, "ocr_images", side_effect=ocr), \
                 patch.object(auto, "focused_lines", return_value=title):
                labels, confidence, evidence = auto.recognize_segment(
                    {"duration_seconds": 100}, (0, 0, 1300, 730), 10, 20, Path(temporary),
                    stage=1, previous_end=7, next_start=40)
            self.assertEqual(labels["song"], "Short summary")
            self.assertGreaterEqual(confidence["song"]["supporting_frames"], 2)
            self.assertGreaterEqual(sum(o["scene"] == "summary" for o in json.loads(Path(evidence).read_text())), 2)

    def test_retained_adaptive_summary_remains_on_replay(self):
        from .fixtures import glyph as line
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            focused = [line("1ST", .48, .18), line("Recovered", .4, .22, .2),
                       line("DOUBLE", .72, .17), line("20", .72, .20)]
            (directory / "ocr.json").write_text(json.dumps([{
                "file": str(directory / f"adaptive-result-{t}.png"), "requested_seconds": t,
                "source_pts_seconds": t, "ocr": [line("PLAY RESULT", .4, .1)],
                "focused_ocr": focused, "phase": "summary", "window": "result"} for t in (37.25, 37.85)]))
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            with patch.object(auto, "capture_game", side_effect=capture) as captured, \
                 patch.object(auto, "ocr_images", side_effect=lambda paths: [{"lines": []} for _ in paths]):
                labels, _, evidence = auto.recognize_segment(
                    {"duration_seconds": 100}, (0, 0, 1300, 730), 10, 20, directory,
                    stage=1, previous_end=7, next_start=90, reuse_summary=True)
            self.assertEqual(labels, {"song": "Recovered", "chart": "D20"})
            self.assertNotIn(37.25, [call.args[2] for call in captured.call_args_list])
            self.assertEqual(sum(o["scene"] == "summary" for o in json.loads(Path(evidence).read_text())), 2)

    def test_retained_float_timestamp_does_not_recapture_existing_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "ocr.json").write_text(json.dumps([{
                "file": str(directory / "result-0.png"), "requested_seconds": 115.29999999999998,
                "source_pts_seconds": 115.3, "ocr": [], "window": "result"}]))
            def capture(record, path, seconds, roi):
                return {"file": str(path), "source_pts_seconds": seconds, "requested_seconds": seconds}
            with patch.object(auto, "capture_game", side_effect=capture) as captured, \
                 patch.object(auto, "ocr_images", side_effect=lambda paths: [{"lines": []} for _ in paths]):
                auto.recognize_segment({"duration_seconds": 150}, (0, 0, 1300, 730),
                                       100, 112.3, directory, previous_end=99, next_start=120)
            self.assertNotIn(115.3, [call.args[2] for call in captured.call_args_list])

    def test_analysis_includes_player_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"source")
            evidence = root / "ocr.json"
            evidence.write_text("[]")
            record = {"path": str(video), "size_bytes": video.stat().st_size,
                      "mtime_ns": video.stat().st_mtime_ns, "duration_seconds": 100,
                      "video_streams": [{"width": 1920, "height": 1080}]}
            detection = {"candidates": [{"start_seconds": 10, "end_seconds": 30, "mean_match_score": 1}]}
            profile = {"hud": (180, 0, 70, 20), "at": 20, "detection": detection}
            player = {"player_id": "p2", "side": "right", "presence": "recognized", "fields": {
                "perfect": {"status": "recognized", "value": 500},
                "chart": {"status": "recognized", "value": "D21", "method": "full_screen_badge_ocr"}}}
            stats = {"players": {"p2": player}, "needs_review": True, "evidence": str(evidence)}
            with patch.object(auto, "media_record", return_value=record), \
                 patch.object(auto, "find_reference", return_value=(20, profile["hud"], {})), \
                 patch.object(auto, "detect", return_value=detection), \
                 patch.object(auto, "discover_profiles", return_value=[profile]), \
                 patch.object(auto, "reference_patch", return_value=b"reference"), \
                 patch.object(auto, "refine_boundary", side_effect=[(10, {"refined": True}), (30, {"refined": True})] * 4), \
                 patch.object(auto, "recognize_segment", return_value=({"song": "Song", "chart": "D12"}, {}, str(evidence))), \
                 patch.object(auto, "recognize_stage", return_value=(4, str(evidence))), \
                 patch.object(auto, "extract_stats", return_value=stats) as extract:
                result = auto.analyze(video, root / "out")
                extract.assert_called_once()
                extract.reset_mock()
            self.assertEqual(result["segments"][0]["results"], stats)
            self.assertEqual(result["segments"][0]["stage"], 4)
            self.assertEqual(result["segments"][0]["chart"], "D21")
            self.assertEqual(result["segments"][0]["chart_correction"]["previous"], "D12")
            self.assertTrue((root / "out/analysis.json").is_file())

    def test_analysis_rejects_candidate_without_song_or_chart_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"source")
            evidence = root / "ocr.json"
            evidence.write_text("[]")
            record = {"path": str(video), "size_bytes": video.stat().st_size,
                      "mtime_ns": video.stat().st_mtime_ns, "duration_seconds": 100,
                      "video_streams": [{"width": 1920, "height": 1080}]}
            detection = {"candidates": [{"start_seconds": 10, "end_seconds": 30, "mean_match_score": 1}]}
            profile = {"hud": (180, 0, 70, 20), "at": 20, "detection": detection}
            with patch.object(auto, "media_record", return_value=record), \
                 patch.object(auto, "find_reference", return_value=(20, profile["hud"], {})), \
                 patch.object(auto, "detect", return_value=detection), \
                 patch.object(auto, "discover_profiles", return_value=[profile]), \
                 patch.object(auto, "reference_patch", return_value=b"reference"), \
                 patch.object(auto, "refine_boundary", side_effect=[(10, {"refined": True}), (30, {"refined": True})]), \
                 patch.object(auto, "recognize_stage", return_value=(None, str(evidence))), \
                 patch.object(auto, "recognize_segment", return_value=({"song": None, "chart": None}, {}, str(evidence))), \
                 patch.object(auto, "extract_stats", return_value={"players": {}, "needs_review": True}) as extract:
                result = auto.analyze(video, root / "out")
            self.assertEqual(result["segments"], [])
            extract.assert_called_once()

    def test_later_credit_summary_recovers_candidate_before_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "source.mp4"
            video.write_bytes(b"source")
            first, second = root / "first.json", root / "second.json"
            first.write_text("[]")
            row = {"song": {"text": "Recovered play", "confidence": 1},
                   "chart": {"text": "S22", "confidence": 1}}
            second.write_text(json.dumps([{"source_pts_seconds": t, "file": f"frame-{t}.png",
                "scene": "summary", "eligible_screen": True, "rows": {"1": row}}
                for t in (90, 91)]))
            record = {"path": str(video), "size_bytes": video.stat().st_size,
                      "mtime_ns": video.stat().st_mtime_ns, "duration_seconds": 120,
                      "video_streams": [{"width": 1920, "height": 1080}]}
            detection = {"candidates": [{"start_seconds": a, "end_seconds": b, "mean_match_score": 1}
                                         for a, b in ((10, 30), (60, 80))]}
            profile = {"hud": (180, 0, 70, 20), "at": 20, "detection": detection}
            with patch.object(auto, "media_record", return_value=record), \
                 patch.object(auto, "find_reference", return_value=(20, profile["hud"], {})), \
                 patch.object(auto, "detect", return_value=detection), \
                 patch.object(auto, "discover_profiles", return_value=[profile]), \
                 patch.object(auto, "reference_patch", return_value=b"reference"), \
                 patch.object(auto, "refine_boundary", side_effect=[(t, {"refined": True}) for t in (10, 30, 60, 80)]), \
                 patch.object(auto, "recognize_stage", side_effect=[(1, str(first)), (2, str(first))]), \
                 patch.object(auto, "recognize_segment", side_effect=[
                     ({"song": None, "chart": None}, {}, str(first)),
                     ({"song": "Second play", "chart": "D20"}, {}, str(second))]), \
                 patch.object(auto, "extract_stats", return_value={"players": {}, "needs_review": True}):
                result = auto.analyze(video, root / "out")
            self.assertEqual(len(result["segments"]), 2)
            self.assertEqual(result["segments"][0]["song"], "Recovered play")
            self.assertEqual(result["segments"][0]["chart"], "S22")
            saved = json.loads((root / "out/segment-001.json").read_text())
            self.assertEqual(saved["song"], "Recovered play")

    def test_alternate_hud_discovery_reaches_beyond_first_ten_minutes(self):
        record = {"duration_seconds": 1200}
        initial = {"hud": (180, 0, 70, 20), "detection": {"candidates": [
            {"start_seconds": 0, "end_seconds": 1000}]}}
        def capture(record, path, seconds, roi):
            return {"file": str(path), "playback_seconds": seconds}
        recognized = [{"lines": [{"text": "STAGE", "box": [.47, .01, .05, .2]}]}]
        additional = {"candidates": [{"start_seconds": 1000, "end_seconds": 1200}]}
        with patch.object(hud_profiles, "capture_game", side_effect=capture) as frames, \
             patch.object(hud_profiles, "ocr_images", return_value=recognized), \
             patch.object(hud_profiles, "detect", return_value=additional) as detect, \
             patch.object(hud_profiles, "write_json"):
            profiles = auto.discover_profiles(record, (0, 0, 1300, 730), Path("unused"), initial)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(frames.call_args.args[2], 1020)
        self.assertEqual(frames.call_args.args[3], (0, 0, 1300, 88))
        detect.assert_called_once()

    def test_merge_profiles_deduplicates_and_preserves_reference(self):
        def profile(start, end, score):
            return {"detection": {"candidates": [{"start_seconds": start, "end_seconds": end,
                                                 "mean_match_score": score}]}}
        merged = auto.merge_profile_candidates([profile(10, 30, .95), profile(12, 30, .96), profile(40, 60, .94)])
        self.assertEqual([item["profile_index"] for item in merged], [1, 2])
        with self.assertRaises(ValueError):
            auto.merge_profile_candidates([profile(10, 30, .95), profile(20, 60, .96)])

    def test_local_source_never_uses_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "local.mp4"
            video.write_bytes(b"local")
            with patch.object(media, "run_download") as invoke:
                path, provenance = auto.resolve_source(str(video))
            invoke.assert_not_called()
            self.assertEqual(path, video.resolve())
            self.assertFalse(provenance["network_used"])

    def test_url_download_path_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(media, "run_download", return_value="PIU_FILE:/outside.mp4\n"):
            with self.assertRaises(ValueError):
                auto.resolve_source("https://www.youtube.com/watch?v=_OE47GBOvB0", Path(temporary))

    def test_cached_youtube_video_skips_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary)
            video = raw / "abc123XYZ00.mkv"
            video.write_bytes(b"video")
            with patch.object(media, "run_download") as invoke:
                path, provenance = auto.resolve_source("abc123XYZ00", raw)
            invoke.assert_not_called()
            self.assertEqual(path, video.resolve())
            self.assertEqual(provenance["kind"], "cached_youtube")

    def test_corrupt_or_missing_inputs_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                auto.analyze(directory / "missing.mp4", directory / "output")
            self.assertFalse((directory / "output").exists())

    def test_decode_refinement_and_no_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video = directory / "input.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                "-f", "lavfi", "-i", "smptebars=s=64x64:r=10:d=4",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                "-c:v", "mpeg4", str(video),
            ], check=True)
            record = auto.media_record(video)
            roi = (0, 0, 64, 64)
            reference = auto.reference_patch(record, roi, 3)
            start, evidence = auto.refine_boundary(record, roi, reference, 2.3, "start", radius=1)
            self.assertAlmostEqual(start, 2, places=1)
            self.assertTrue(evidence["refined"])
            end, evidence = auto.refine_boundary(record, roi, reference, 6.3, "end", radius=1)
            self.assertAlmostEqual(end, 6, places=1)
            self.assertTrue(evidence["refined"])
            unchanged, evidence = auto.refine_boundary(record, roi, reference, 4, "start", radius=.5)
            self.assertEqual(unchanged, 4)
            self.assertFalse(evidence["refined"])


if __name__ == "__main__":
    unittest.main()
