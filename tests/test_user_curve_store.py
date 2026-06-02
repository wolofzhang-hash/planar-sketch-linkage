import unittest

from planar_sketch.core.user_curve_store import deserialize_user_curve_store, serialize_user_curve_store


class UserCurveStoreTest(unittest.TestCase):
    def test_user_curve_store_roundtrip(self):
        store = {
            "target": {
                "name": "target",
                "x": [0.0, 1.0],
                "y": [10.0, 20.0],
                "x_label": "Angle",
                "y_label": "Displacement",
                "source_type": "imported",
            }
        }
        payload = serialize_user_curve_store(store)
        self.assertEqual(len(payload), 1)
        restored = deserialize_user_curve_store(payload)
        self.assertEqual(restored["target"]["y"], [10.0, 20.0])

    def test_deserialize_skips_invalid_rows(self):
        restored = deserialize_user_curve_store([
            {"name": "curve_a", "x": [0], "y": [1]},
            {"name": "", "x": [0], "y": [2]},
            "bad-row",
        ])
        self.assertEqual(list(restored.keys()), ["curve_a"])


if __name__ == "__main__":
    unittest.main()
