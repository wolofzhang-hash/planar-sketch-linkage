import csv
import os
import tempfile
import unittest

from planar_sketch.core.case_run_manager import CaseRunManager
from planar_sketch.core.replay_service import ReplayService
from planar_sketch.core.run_models import CaseSpec, ReplayFrame


class CaseRunManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = CaseRunManager(self.tmp.name, project_uuid="proj-1")
        self.spec30 = CaseSpec.from_dict({
            "schema_version": "1.0",
            "target_input_deg": 30.0,
            "target_input_deg_list": [30.0],
            "driver": {"enabled": True, "type": "angle", "pivot": 0, "tip": 1, "sweep_start": 0.0, "sweep_end": 30.0},
            "drivers": [{"enabled": True, "type": "angle", "pivot": 0, "tip": 1, "sweep_start": 0.0, "sweep_end": 30.0}],
            "sweep": {"start_deg": 0.0, "end_deg": 30.0, "step_count": 3},
            "record_pose": True,
        })
        self.specm40 = CaseSpec.from_dict({
            "schema_version": "1.0",
            "target_input_deg": -40.0,
            "target_input_deg_list": [-40.0],
            "driver": {"enabled": True, "type": "angle", "pivot": 0, "tip": 1, "sweep_start": 0.0, "sweep_end": -40.0},
            "drivers": [{"enabled": True, "type": "angle", "pivot": 0, "tip": 1, "sweep_start": 0.0, "sweep_end": -40.0}],
            "sweep": {"start_deg": 0.0, "end_deg": -40.0, "step_count": 3},
            "record_pose": True,
        })
        self.model = {"points": [{"id": 0, "x": 0.0, "y": 0.0}]}
        self.frames30 = [
            ReplayFrame({"time": 0, "input_deg": 0.0, "driver_deg": [0.0], "pose_points": [[0, 0.0, 0.0]]}),
            ReplayFrame({"time": 1, "input_deg": 30.0, "driver_deg": [30.0], "pose_points": [[0, 1.0, 0.0]]}),
        ]
        self.framesm40 = [
            ReplayFrame({"time": 0, "input_deg": 360.0, "driver_deg": [360.0], "pose_points": [[0, 0.0, 0.0]]}),
            ReplayFrame({"time": 1, "input_deg": 320.0, "driver_deg": [320.0], "pose_points": [[0, -1.0, 0.0]]}),
        ]
        self.status = {"success": True, "reason": "ok", "elapsed_sec": 0.1}

    def tearDown(self):
        self.tmp.cleanup()

    def _read_input_deg(self, frame_path):
        with open(frame_path, "r", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        return [row["input_deg"] for row in rows]

    def test_current_case_run_and_last_run_are_separate(self):
        case = self.manager.create_case(self.spec30.to_dict())
        self.manager.save_current_run(case.name, self.spec30, self.model, self.frames30, self.status)
        self.manager.save_last_run(self.specm40, self.model, self.framesm40, self.status)

        case_frame_path = os.path.join(self.tmp.name, "runs", case.name, "current", "results", "frames.csv")
        last_frame_path = os.path.join(self.tmp.name, "runs", "_last", "current", "results", "frames.csv")
        self.assertEqual(self._read_input_deg(case_frame_path), ["0.0", "30.0"])
        self.assertEqual(self._read_input_deg(last_frame_path), ["360.0", "320.0"])

    def test_run_case_json_uses_executed_spec(self):
        case = self.manager.create_case(self.spec30.to_dict())
        stored = self.manager.load_case_spec(case.name)
        self.assertEqual(stored.get("target_input_deg"), 30.0)
        executed = self.spec30.to_dict()
        executed["target_input_deg"] = 45.0
        executed["curve_target"] = {"x": [0, 1], "y": [10, 20]}
        self.manager.save_current_run(case.name, executed, self.model, self.frames30, self.status)
        run_case = os.path.join(self.tmp.name, "runs", case.name, "current", "case.json")
        with open(run_case, "r", encoding="utf-8") as fh:
            payload = __import__("json").load(fh)
        self.assertEqual(payload.get("target_input_deg"), 45.0)
        self.assertEqual((payload.get("curve_target") or {}).get("y"), [10, 20])

    def test_case_rename_updates_display_name_only(self):
        case = self.manager.create_case(self.spec30.to_dict())
        self.assertTrue(case.name.startswith("case_"))
        self.assertEqual(case.display_name, "1")
        self.assertTrue(self.manager.rename_case(case.name, "My Case"))
        listed = self.manager.list_cases()[0]
        self.assertEqual(listed.name, case.name)
        self.assertEqual(listed.display_name, "My Case")
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "cases", f"{case.name}.case.json")))


    def test_case_operations_require_internal_case_id(self):
        case = self.manager.create_case(self.spec30.to_dict())
        self.assertTrue(self.manager.rename_case(case.name, "My Case"))
        self.manager.save_current_run(case.name, self.spec30, self.model, self.frames30, self.status)
        with self.assertRaises(KeyError):
            self.manager.save_current_run("My Case", self.spec30, self.model, self.frames30, self.status)
        self.assertFalse(self.manager.delete_case_runs("My Case"))
        records = self.manager.list_run_records(case.name)
        self.assertEqual(len(records), 1)


    def test_delete_case_removes_current_run_and_clears_last_run(self):
        case = self.manager.create_case(self.spec30.to_dict())
        run_dir = self.manager.save_current_run(case.name, self.spec30, self.model, self.frames30, self.status)
        self.assertTrue(os.path.isdir(run_dir))
        self.assertEqual(self.manager.last_run_path(), run_dir)

        self.assertTrue(self.manager.delete_case(case.name))
        self.assertFalse(os.path.isdir(os.path.join(self.tmp.name, "runs", case.name)))
        self.assertIsNone(self.manager.last_run_path())

    def test_last_run_path_ignores_missing_directory(self):
        stale = os.path.join(self.tmp.name, "runs", "missing", "current")
        with open(os.path.join(self.tmp.name, "runs", "last_run.txt"), "w", encoding="utf-8") as fh:
            fh.write(stale)
        self.assertIsNone(self.manager.last_run_path())

    def test_delete_latest_duplicate_hash_remaps_to_existing_case(self):
        first = self.manager.create_case(self.spec30.to_dict())
        second = self.manager.create_case(self.spec30.to_dict())
        self.assertNotEqual(first.name, second.name)

        self.assertTrue(self.manager.delete_case(second.name))
        reused = self.manager.get_or_create_case(self.spec30.to_dict())
        self.assertEqual(reused.name, first.name)

    def test_replay_validation_reports_missing_files(self):
        case = self.manager.create_case(self.spec30.to_dict())
        self.manager.save_current_run(case.name, self.spec30, self.model, self.frames30, self.status)
        records = self.manager.list_run_records(case.name)
        record = records[0]
        replay = ReplayService()
        self.assertEqual(replay.validate_run(record), [])
        os.remove(os.path.join(record.path, "case.json"))
        errors = replay.validate_run(record)
        self.assertTrue(any("case.json" in err for err in errors))
        with self.assertRaises(FileNotFoundError):
            replay.load_frame_rows(record)

    def test_list_run_records_and_replay_bundle(self):
        case = self.manager.create_case(self.spec30.to_dict())
        self.manager.save_current_run(case.name, self.spec30, self.model, self.frames30, self.status)
        records = self.manager.list_run_records(case.name)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].run_id, "current")

        replay = ReplayService()
        bundle = replay.load_bundle(records[0])
        self.assertEqual(bundle.run.run_id, "current")
        self.assertEqual(len(bundle.frames), 2)
        self.assertTrue(replay.run_contains_pose_points(records[0]))


if __name__ == "__main__":
    unittest.main()
