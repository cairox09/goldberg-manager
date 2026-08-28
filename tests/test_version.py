import unittest

from goldberg_manager.cli import APP_VERSION as CLI_APP_VERSION
from goldberg_manager.version import APP_VERSION


class RuntimeVersionTests(unittest.TestCase):
    def test_runtime_version_remains_0_3_0(self) -> None:
        self.assertEqual(APP_VERSION, "0.3.0")

    def test_app_version_remains_available_from_cli(self) -> None:
        self.assertEqual(CLI_APP_VERSION, "0.3.0")

    def test_cli_app_version_matches_runtime_version(self) -> None:
        self.assertEqual(CLI_APP_VERSION, APP_VERSION)


if __name__ == "__main__":
    unittest.main()
