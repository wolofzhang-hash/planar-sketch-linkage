import json
import unittest
from pathlib import Path

from planar_sketch.ui.i18n import LANGUAGES, load_languages, tr


class I18nExternalizationTest(unittest.TestCase):
    def test_locale_files_are_loaded(self):
        loaded = load_languages()
        self.assertIn("en", loaded)
        self.assertIn("zh", loaded)
        self.assertEqual(loaded["en"]["tab.animation"], "Animation")
        self.assertEqual(loaded["zh"]["tab.animation"], "动画")

    def test_tr_uses_external_data(self):
        self.assertEqual(tr("en", "table.state"), LANGUAGES["en"]["table.state"])
        self.assertEqual(tr("zh", "table.state"), LANGUAGES["zh"]["table.state"])

    def test_locale_json_exists(self):
        base = Path(__file__).resolve().parents[1] / "planar_sketch" / "ui" / "locales"
        for lang in ("en", "zh"):
            path = base / f"{lang}.json"
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
            self.assertIn("table.state", data)


if __name__ == "__main__":
    unittest.main()
