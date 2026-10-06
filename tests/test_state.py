import importlib.util
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location("remote_state", Path(__file__).resolve().parents[1] / "remote/state.py")
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
CFG = {"WORKBENCH_NAME": "test-box", "CLOUDCLI_VERSION": "1.37.3", "CODEX_VERSION": "0.156.1"}
RESTIC = {k: "fake" for k in ("RESTIC_REPOSITORY", "RESTIC_PASSWORD", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION")}

class StateTests(unittest.TestCase):
    def test_sqlite_wal_and_auth_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source", Path(tmp) / "target"
            source.mkdir()
            (source / "auth.json").write_text('"secret"')
            with sqlite3.connect(source / "state.sqlite") as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE messages (text TEXT)")
                db.execute("INSERT INTO messages VALUES ('durable')")
                db.commit()
                state.copy_state(source, target, exclude_auth=True)
            self.assertFalse((target / "auth.json").exists())
            self.assertFalse((target / "state.sqlite-wal").exists())
            with sqlite3.connect(target / "state.sqlite") as db:
                self.assertEqual(db.execute("SELECT text FROM messages").fetchone()[0], "durable")

    def test_symlink_cannot_copy_outside_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "escape").symlink_to("/etc/passwd")
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                state.copy_state(source, Path(tmp) / "dest")

    def test_corruption_inventory_and_version_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "history.jsonl").write_text("history")
            state.make_manifest(stage, CFG)
            state.verify_manifest(stage, CFG)
            with self.assertRaisesRegex(RuntimeError, "versions"):
                state.verify_manifest(stage, CFG | {"CODEX_VERSION": "0.0.1"})
            (stage / "extra").write_text("untracked")
            with self.assertRaisesRegex(RuntimeError, "inventory"):
                state.verify_manifest(stage, CFG)
            (stage / "extra").unlink()
            (stage / "history.jsonl").write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                state.verify_manifest(stage, CFG)

    def test_nested_manifest_is_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "plugin").mkdir()
            (stage / "plugin/manifest.json").write_text("{}")
            manifest = state.make_manifest(stage, CFG)
            self.assertIn("plugin/manifest.json", manifest["files"])

    def test_restore_error_does_not_become_empty_history(self):
        obj = state.State(CFG | RESTIC | {"RESTIC_INIT": "false", "RESTORE_MODE": "auto"})
        obj.snapshots = Mock(side_effect=RuntimeError("network unavailable"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(state, "BASE", Path(tmp)):
            with self.assertRaisesRegex(RuntimeError, "network unavailable"):
                obj.restore()
            self.assertFalse((Path(tmp) / "restored").exists())

    def test_backup_failure_resumes_services(self):
        obj = state.State(CFG | RESTIC)
        obj.quiesce = Mock(side_effect=RuntimeError("still running"))
        obj.services = Mock()
        with self.assertRaises(RuntimeError):
            obj.backup("nonce", leave_stopped=True)
        obj.services.assert_called_once_with("start")

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_real_git_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(["git", *map(str, args)], stderr=subprocess.DEVNULL, text=True)
            git("init", "--bare", root / "remote.git")
            git("clone", root / "remote.git", root / "workspace/project")
            repo = root / "workspace/project"
            git("-C", repo, "config", "user.email", "test@example.com")
            git("-C", repo, "config", "user.name", "Test")
            (repo / "file").write_text("one")
            git("-C", repo, "add", ".")
            git("-C", repo, "commit", "-m", "initial")
            execute = lambda argv: subprocess.check_output(argv, stderr=subprocess.DEVNULL, text=True)
            with self.assertRaisesRegex(RuntimeError, "Unpushed"):
                state.git_inventory(root / "workspace", execute)
            git("-C", repo, "push", "-u", "origin", "HEAD")
            self.assertEqual(len(state.git_inventory(root / "workspace", execute)), 1)
            (repo / "file").write_text("two")
            with self.assertRaisesRegex(RuntimeError, "Uncommitted"):
                state.git_inventory(root / "workspace", execute)
            git("-C", repo, "stash")
            with self.assertRaisesRegex(RuntimeError, "stashes"):
                state.git_inventory(root / "workspace", execute)


class CodexTmpSymlinkTests(unittest.TestCase):
    def test_codex_tmp_symlinks_are_skipped_but_other_symlinks_still_block(self):
        import tempfile
        from pathlib import Path
        copy_state = state.copy_state
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "codex", Path(tmp) / "out"
            (src / "tmp" / "arg0" / "x").mkdir(parents=True)
            (src / "tmp" / "arg0" / "x" / "apply_patch").symlink_to("/bin/true")
            (src / "history.jsonl").write_text("{}")
            copy_state(src, dst, skip=("tmp",))
            self.assertTrue((dst / "history.jsonl").exists())
            self.assertFalse((dst / "tmp").exists())
            (src / "bad").symlink_to("/etc/passwd")
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                copy_state(src, Path(tmp) / "out2", skip=("tmp",))


class CloneTests(unittest.TestCase):
    def test_clone_success_exists_failure_and_token_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            origin = tmp / "src" / "demo"
            origin.mkdir(parents=True)
            for cmd in (["git", "init", "-q"], ["git", "-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "--allow-empty", "-m", "x"]):
                subprocess.run(cmd, cwd=origin, check=True)
            workspace = tmp / "ws"
            workspace.mkdir()
            cfg = {"CLONE_REPOS": "own/demo,own/missing,--evil/x", "GH_TOKEN": "tok123"}
            lines = state.clone_repos(cfg, workspace=workspace, log_path=tmp / "log", prefix=(), url=str(tmp / "src") + "/{repo}")
            self.assertEqual(lines[0][:6], "FAILED")  # own/demo path is src/own/demo, absent
            self.assertTrue(any(x.startswith("FAILED own/missing") for x in lines))
            self.assertIn("FAILED --evil/x: not a valid owner/repo name", lines)
            (tmp / "src" / "own").mkdir()
            shutil.move(str(origin), str(tmp / "src" / "own" / "demo"))
            lines = state.clone_repos({"CLONE_REPOS": "own/demo"}, workspace=workspace, log_path=tmp / "log", prefix=(), url=str(tmp / "src") + "/{repo}")
            self.assertTrue(lines[0].startswith("cloned own/demo"))
            self.assertTrue((workspace / "demo" / ".git").exists())
            lines = state.clone_repos({"CLONE_REPOS": "own/demo"}, workspace=workspace, log_path=tmp / "log", prefix=(), url="x")
            self.assertTrue(lines[0].startswith("exists own/demo"))
