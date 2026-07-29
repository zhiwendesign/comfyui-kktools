from __future__ import annotations

import unittest

from kktools_settings.settings_routes import _models_url


class SettingsRoutesTests(unittest.TestCase):
    def test_models_url_appends_v1_for_api_root(self):
        self.assertEqual(
            _models_url("https://api.example.com"),
            "https://api.example.com/v1/models",
        )

    def test_models_url_does_not_duplicate_existing_v1(self):
        self.assertEqual(
            _models_url("https://api.example.com/v1/"),
            "https://api.example.com/v1/models",
        )

    def test_models_url_preserves_explicit_models_endpoint(self):
        self.assertEqual(
            _models_url("https://api.example.com/v1/models"),
            "https://api.example.com/v1/models",
        )


if __name__ == "__main__":
    unittest.main()
