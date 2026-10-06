import argparse
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock
from workbench.cli import Controller, validate_server, write_json
from workbench.config import Error, REMOTE_KEYS, DEFAULTS
from workbench.hetzner import Hetzner

SERVER = {"id": 123, "labels": {"managed-by": "cli-workbench", "workbench": "test-box", "instance": "instance-a"}}

class LifecycleTests(unittest.TestCase):
    def controller(self, tmp):
        ctl = Controller({"WORKBENCH_NAME": "test-box", "HCLOUD_TOKEN": "secret"}, Path(tmp))
        ctl.api = Mock()
        ctl.api.get.return_value = SERVER
        ctl.api.servers.return_value = []
        ctl.remote = Mock()
        return ctl

    def args(self):
        return argparse.Namespace(confirm="test-box", quiesce=True, discard_unbacked=False, confirm_id=None)

    def test_foreign_server_rejected(self):
        with self.assertRaises(Error):
            validate_server(SERVER, "another-box")
        with self.assertRaises(Error):
            validate_server(SERVER, "test-box", "old-instance")

    def test_backup_failure_never_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp)
            ctl.remote.side_effect = Error("backup failed")
            with self.assertRaises(Error):
                ctl.destroy(SERVER, self.args())
            ctl.api.delete.assert_not_called()

    def test_stale_receipt_never_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp)
            ctl.remote.return_value = json.dumps({"server_id": 123, "instance": "instance-a", "nonce": "old", "snapshot": "a" * 64, "verified": True})
            with self.assertRaises(Error):
                ctl.destroy(SERVER, self.args())
            ctl.api.delete.assert_not_called()

    def test_verified_backup_precedes_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp)
            events = []
            def remote(server, action, nonce):
                events.append("backup")
                return json.dumps({"server_id": 123, "instance": "instance-a", "nonce": nonce, "snapshot": "a" * 64, "verified": True})
            ctl.remote.side_effect = remote
            ctl.api.delete.side_effect = lambda _: events.append("delete")
            ctl.destroy(SERVER, self.args())
            self.assertEqual(events, ["backup", "delete"])

    def test_explicit_discard_requires_exact_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp)
            args = self.args()
            args.discard_unbacked, args.confirm_id = True, "999"
            with self.assertRaises(Error):
                ctl.destroy(SERVER, args)
            ctl.api.delete.assert_not_called()

    def test_unknown_create_outcome_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp)
            write_json(ctl.state_path, {"instance": "pending"})
            with self.assertRaisesRegex(Error, "unknown"):
                ctl.start()
            ctl.api.create.assert_not_called()

    def test_cloud_init_has_no_credentials(self):
        api = Hetzner("secret")
        api.request = Mock(return_value={"server": SERVER})
        cfg = {"WORKBENCH_NAME": "test-box", "HCLOUD_SERVER_TYPE": "cpx32", "HCLOUD_LOCATION": "nbg1", "HCLOUD_IMAGE": "ubuntu-24.04", "HCLOUD_SSH_KEY_ID": "12", "OPENAI_API_KEY": "do-not-leak"}
        api.create(cfg, "instance-a")
        self.assertNotIn("do-not-leak", json.dumps(api.request.call_args.args))
        self.assertNotIn("HCLOUD_TOKEN", REMOTE_KEYS)
        self.assertNotIn("SSH_PRIVATE_KEY", REMOTE_KEYS)

    def test_upload_contains_runtime_and_only_remote_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp)
            ctl.cfg = DEFAULTS | ctl.cfg | {"OPENAI_API_KEY": "agent-secret"}
            ctl.ssh = Mock(return_value="")
            ctl.deploy(SERVER)
            payload = ctl.ssh.call_args_list[0].args[2]
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                self.assertIn("remote/bootstrap.sh", archive.getnames())
                cfg = json.load(archive.extractfile("config.json"))
                self.assertEqual(cfg["OPENAI_API_KEY"], "agent-secret")
                self.assertNotIn("HCLOUD_TOKEN", cfg)
            for call in ctl.ssh.call_args_list:
                self.assertNotIn("agent-secret", call.args[1])

    def test_state_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "instance.json"
            write_json(path, {"id": 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class StartProgressTests(unittest.TestCase):
    def controller(self, tmp, statuses):
        cfg = DEFAULTS | {"WORKBENCH_NAME": "test-box", "HCLOUD_TOKEN": "secret", "WAIT_SECONDS": "60",
                          "PUBLIC_HOSTNAME": "agents.example.com"}
        ctl = Controller(cfg, Path(tmp))
        write_json(ctl.state_path, {"id": 123, "instance": "instance-a"})
        ctl.api = Mock()
        ctl.api.servers.return_value = [SERVER]
        ctl.api.get.return_value = dict(SERVER, status="running")
        ctl.ssh = Mock(side_effect=statuses)
        ctl.deploy = Mock()
        return ctl

    def run_start(self, ctl):
        import contextlib
        import time
        from unittest import mock
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(time, "sleep"):
            ctl.start()
        return out.getvalue()

    def test_progress_shows_ssh_reason_stage_and_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp, [Error("Remote command failed (exit 255): Permission denied (publickey)."),
                                        "empty", "installing|==> [5/8] Installing CloudCLI", "ready"])
            text = self.run_start(ctl)
            self.assertIn("SSH not ready yet: Remote command failed (exit 255): Permission denied", text)
            self.assertIn("Uploading installer", text)
            self.assertIn("Installing: [5/8] Installing CloudCLI", text)
            self.assertIn("Installed.", text)
            ctl.deploy.assert_called_once()

    def test_server_deleted_externally_gives_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctl = self.controller(tmp, [])
            ctl.api.get.side_effect = Error("Hetzner GET /servers/123 returned HTTP 404")
            with self.assertRaisesRegex(Error, "no longer exists"):
                self.run_start(ctl)
            self.assertFalse(ctl.state_path.exists())


class KeyCheckTests(unittest.TestCase):
    def test_key_matches_and_mismatch_blocks_creation(self):
        import shutil
        import subprocess
        if not shutil.which("ssh-keygen"):
            self.skipTest("ssh-keygen not installed")
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "k"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
            pub = (Path(tmp) / "k.pub").read_text().strip()
            cfg = DEFAULTS | {"WORKBENCH_NAME": "test-box", "HCLOUD_TOKEN": "x", "HCLOUD_SSH_KEY_ID": "5",
                              "SSH_PRIVATE_KEY": str(key)}
            ctl = Controller(cfg, Path(tmp))
            ctl.api = Mock()
            ctl.api.servers.return_value = []
            ctl.api.ssh_key.return_value = {"public_key": pub + " termux"}
            ctl.check_key()
            ctl.api.ssh_key.return_value = {"public_key": "ssh-ed25519 AAAAdifferent other"}
            with self.assertRaisesRegex(Error, "different key"):
                ctl.start()
            ctl.api.create.assert_not_called()
            locked = Path(tmp) / "locked"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "pass", "-f", str(locked)], check=True)
            ctl.cfg = cfg | {"SSH_PRIVATE_KEY": str(locked)}
            with self.assertRaisesRegex(Error, "passphrase"):
                ctl.check_key()
