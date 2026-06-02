import unittest

from planar_sketch.core.expression_registry import PARAMETER_ALLOWED_FUNCTIONS, PARAMETER_FUNCTIONS
from planar_sketch.core.expression_service import eval_param_expression


class ExpressionRegistryTest(unittest.TestCase):
    def test_ui_and_backend_cover_same_parameter_functions(self):
        ui_funcs = {token[:-1] for token in PARAMETER_FUNCTIONS if token.endswith('(')}
        backend_funcs = {k for k in PARAMETER_ALLOWED_FUNCTIONS.keys() if k not in {"pi", "E"}}
        self.assertTrue(ui_funcs.issubset(backend_funcs))

    def test_extended_parameter_functions_evaluate(self):
        value, err = eval_param_expression('log10(100) + floor(1.9) + ceil(2.1)', {})
        self.assertIsNone(err)
        self.assertAlmostEqual(value, 6.0)


if __name__ == '__main__':
    unittest.main()
