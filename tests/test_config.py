import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench.config import Error, load, read_env

class ConfigTests(unittest.TestCase):
    def test_values_never_expanded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "env"
            literal = "$(touch /tmp/should-not-exist)$HOME" + chr(96) + "id" + chr(96)
            p.write_text('VALUE="' + literal + '"\n')
            self.assertEqual(read_env(p)["VALUE"], literal)

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "env"
            p.write_text("AGENTS=codex\nAGENTS=claude\n")
            with self.assertRaises(Error):
                read_env(p)

    def test_example_missing_credentials_blocks_creation(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(load(".env.example", full=False)["AGENTS"], "codex")
            with self.assertRaisesRegex(Error, "Missing configuration"):
                load(".env.example")

    def test_unsupported_provider_unpinned_version_unknown_key(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            p = Path(tmp) / "env"
            for value in ("CLOUD_PROVIDER=aws", "CODEX_VERSION=latest", "UNKNOWN=true"):
                p.write_text(value)
                with self.subTest(value=value), self.assertRaises(Error):
                    load(p, full=False)
