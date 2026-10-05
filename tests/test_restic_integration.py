"""Encrypted local integration tests. No provider accounts or cloud resources."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from test_state import state, CFG, RESTIC

@unittest.skipUnless(shutil.which("restic"), "install restic for encrypted backup integration")
class ResticIntegration(unittest.TestCase):
    def test_encrypted_round_trip_and_wrong_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "state"
            source.mkdir()
            (source / "sessions.jsonl").write_text('{"message":"preserve me"}\n')
            env = os.environ | {"RESTIC_REPOSITORY": str(root / "repository"), "RESTIC_PASSWORD": "integration-only-password", "RESTIC_CACHE_DIR": str(root / "cache")}
            def run(*args, **kwargs):
                return subprocess.run(["restic", *args], env=kwargs.get("env", env), capture_output=True, text=True)
            self.assertEqual(run("init").returncode, 0)
            self.assertEqual(run("backup", str(source)).returncode, 0)
            self.assertEqual(run("restore", "latest", "--target", str(root / "restored"), "--verify").returncode, 0)
            restored = root / "restored" / str(source).lstrip("/") / "sessions.jsonl"
            self.assertEqual(restored.read_bytes(), (source / "sessions.jsonl").read_bytes())
            self.assertNotEqual(run("snapshots", env=env | {"RESTIC_PASSWORD": "wrong"}).returncode, 0)

    def test_workbench_backup_receipt_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, home = root / "runtime", root / "home"
            base.mkdir()
            (home / ".codex").mkdir(parents=True)
            (home / ".cloudcli").mkdir()
            (home / ".codex/sessions.jsonl").write_text("conversation\n")
            (home / ".codex/auth.json").write_text("secret")
            with sqlite3.connect(home / ".cloudcli/auth.db") as db:
                db.execute("CREATE TABLE preferences (value TEXT)")
                db.execute("INSERT INTO preferences VALUES ('push-key')")
            cfg = CFG | RESTIC | {
                "RESTIC_REPOSITORY": str(root / "repository"),
                "RESTIC_PASSWORD": "integration-only-password",
                "PERSIST_CODEX_AUTH": "false", "RESTORE_MODE": "auto", "RESTIC_INIT": "false",
                "server_id": 123, "instance": "test", "ACCESS_MODE": "ssh",
            }
            with patch.object(state, "BASE", base), patch.object(state, "DEV_HOME", home), patch.object(state, "git_inventory", return_value=[]):
                obj = state.State(cfg)
                obj.quiesce, obj.services = Mock(), Mock()
                obj.restic("init")
                receipt = obj.backup("nonce", leave_stopped=True)
                self.assertTrue(receipt["verified"])
                self.assertEqual(len(receipt["snapshot"]), 64)
                obj.services.assert_not_called()
                shutil.rmtree(home)
                home.mkdir()
                obj.restore()
                self.assertEqual((home / ".codex/sessions.jsonl").read_text(), "conversation\n")
                self.assertFalse((home / ".codex/auth.json").exists())
                with sqlite3.connect(home / ".cloudcli/auth.db") as db:
                    self.assertEqual(db.execute("SELECT value FROM preferences").fetchone()[0], "push-key")
