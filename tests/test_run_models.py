import unittest

from planar_sketch.core.run_models import CaseSpec, ReplayFrame, RunRecord
from planar_sketch.version import CASE_SCHEMA_VERSION


class RunModelsTest(unittest.TestCase):
    def test_case_spec_roundtrip(self):
        src = {
            "schema_version": "1.0",
            "name": "case-A",
            "target_input_deg": 30.0,
            "target_input_deg_list": [30.0],
            "analysis_mode": "quasi_static",
            "record_pose": True,
            "driver": {"enabled": True, "type": "angle", "pivot": 0, "tip": 1, "sweep_start": 0.0, "sweep_end": 30.0},
            "drivers": [{"enabled": True, "type": "angle", "pivot": 0, "tip": 1, "sweep_start": 0.0, "sweep_end": 30.0}],
            "output": {"enabled": True, "pivot": 3, "tip": 2},
            "outputs": [{"enabled": True, "pivot": 3, "tip": 2}],
            "sweep": {"start_deg": 0.0, "end_deg": 30.0, "step_count": 200},
            "solver": {"name": "scipy"},
            "measurements": {"signals": ["input_deg"]},
            "custom_field": "keep-me",
        }
        spec = CaseSpec.from_dict(src)
        self.assertEqual(spec.driver.sweep_end, 30.0)
        self.assertEqual(spec.sweep.end_deg, 30.0)
        self.assertEqual(spec.extra["custom_field"], "keep-me")

        out = spec.to_dict()
        self.assertEqual(out["custom_field"], "keep-me")
        self.assertEqual(out["driver"]["sweep_end"], 30.0)
        self.assertEqual(out["sweep"]["end_deg"], 30.0)


    def test_default_case_schema_matches_version_constant(self):
        self.assertEqual(CaseSpec.from_dict({}).schema_version, CASE_SCHEMA_VERSION)
        self.assertEqual(CaseSpec().to_dict()["schema_version"], CASE_SCHEMA_VERSION)

    def test_replay_frame_and_run_record_roundtrip(self):
        frame = ReplayFrame.from_dict({"time": 0, "input_deg": 30.0})
        self.assertEqual(frame.to_dict()["input_deg"], 30.0)

        record = RunRecord.from_dict({"run_id": "current", "path": "/tmp/x", "success": True})
        self.assertTrue(record.success)
        self.assertEqual(record.to_dict()["run_id"], "current")


if __name__ == "__main__":
    unittest.main()
