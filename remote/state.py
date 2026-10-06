#!/usr/bin/env python3
"""Root-owned state operations. Agent/UI processes run as dev."""
import argparse
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

BASE = Path("/var/lib/cli-workbench")
CONFIG = Path("/opt/cli-workbench/config.json")
DEV_HOME = Path("/home/dev")
WORKSPACE = Path("/workspace")

def run(argv, **kwargs):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} failed with exit {result.returncode}")
    return result.stdout

def dev_run(argv, **kwargs):
    kwargs.setdefault("cwd", str(DEV_HOME))
    return run(["runuser", "-u", "dev", "--", "env", "HOME=/home/dev", *argv], **kwargs)

def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def copy_state(source, target, exclude_auth=False, skip=()):
    """Copy regular state and snapshot SQLite through backup(), including WAL."""
    target.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return
    if source.is_symlink():
        raise RuntimeError("State root must not be a symlink")
    for entry in sorted(source.iterdir()):
        if exclude_auth and entry.name == "auth.json":
            continue
        if entry.name in skip:
            continue
        if entry.is_symlink():
            raise RuntimeError(f"State symlink needs manual review: {entry.name}")
        destination = target / entry.name
        if entry.is_dir():
            copy_state(entry, destination)
        elif entry.is_file():
            if entry.name.endswith(("-wal", "-shm")):
                parent = entry.with_name(entry.name.rsplit("-", 1)[0])
                if parent.is_file():
                    with parent.open("rb") as stream:
                        if stream.read(16) == b"SQLite format 3\x00":
                            continue
            with entry.open("rb") as stream:
                sqlite = stream.read(16) == b"SQLite format 3\x00"
            if sqlite:
                with closing(sqlite3.connect(entry.as_uri() + "?mode=ro", uri=True)) as src:
                    with closing(sqlite3.connect(destination)) as dst:
                        src.backup(dst)
                        dst.execute("PRAGMA journal_mode=DELETE")
                        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise RuntimeError("SQLite integrity check failed")
            else:
                shutil.copyfile(entry, destination)

def make_manifest(stage, cfg):
    manifest = {"schema": 1, "workbench": cfg["WORKBENCH_NAME"],
                "cloudcli_version": cfg["CLOUDCLI_VERSION"], "codex_version": cfg["CODEX_VERSION"],
                "created": int(time.time()), "files": {}}
    for file in sorted(stage.rglob("*")):
        if file.is_file() and file != stage / "manifest.json":
            manifest["files"][str(file.relative_to(stage))] = file_hash(file)
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest

def verify_manifest(stage, cfg):
    manifest = json.loads((stage / "manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("workbench") != cfg["WORKBENCH_NAME"]:
        raise RuntimeError("Backup identity/schema mismatch")
    for key, setting in (("cloudcli_version", "CLOUDCLI_VERSION"), ("codex_version", "CODEX_VERSION")):
        if manifest[key] != cfg[setting]:
            raise RuntimeError("Backup versions differ. Restore using recorded versions before upgrading")
    actual = set()
    for file in stage.rglob("*"):
        if file.is_symlink():
            raise RuntimeError("Backup contains a symlink")
        if file.is_file() and file != stage / "manifest.json":
            actual.add(str(file.relative_to(stage)))
    if actual != set(manifest["files"]):
        raise RuntimeError("Backup file inventory mismatch")
    for relative, digest in manifest["files"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or file_hash(stage / path) != digest:
            raise RuntimeError("Backup checksum/path validation failed")
    return manifest

def git_inventory(root=WORKSPACE, execute=dev_run):
    repositories = []
    if not root.exists():
        return repositories
    for directory, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", ".next", ".cache", "vendor")]
        path = Path(directory)
        if not (path / ".git").exists():
            continue
        command = ["git", "-C", str(path)]
        if execute(command + ["status", "--porcelain", "--untracked-files=all"]).strip():
            raise RuntimeError(f"Uncommitted/untracked files in {path}; commit and push first")
        if execute(command + ["stash", "list"]).strip():
            raise RuntimeError(f"Unpreserved Git stashes in {path}; apply/commit/push or explicitly remove them")
        if not execute(command + ["remote"]).split():
            raise RuntimeError(f"No remote for {path}")
        execute(command + ["fetch", "--all", "--prune"])
        if execute(command + ["rev-list", "HEAD", "--branches", "--not", "--remotes"]).strip():
            raise RuntimeError(f"Unpushed commits in {path}; push all local branches first")
        repositories.append({"path": str(path), "head": execute(command + ["rev-parse", "HEAD"]).strip(),
                             "branch": execute(command + ["rev-parse", "--abbrev-ref", "HEAD"]).strip()})
    return repositories

class State:
    def __init__(self, cfg):
        self.cfg = cfg
        self.env = os.environ.copy()
        for key in ("RESTIC_REPOSITORY", "RESTIC_PASSWORD", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
            self.env[key] = cfg[key]
        self.env["RESTIC_CACHE_DIR"] = str(BASE / "restic-cache")
        self.tag = "workbench=" + cfg["WORKBENCH_NAME"]

    def restic(self, *args):
        return run(["restic", *args], env=self.env, timeout=3600)

    def services(self, action):
        names = ["workbench-cloudcli"]
        if self.cfg["ACCESS_MODE"] == "cloudflare":
            names.append("workbench-tunnel")
        run(["systemctl", action, *names])

    def quiesce(self):
        if subprocess.run(["systemctl", "is-active", "--quiet", "workbench-bootstrap"]).returncode == 0:
            raise RuntimeError("Bootstrap is still running; wait before taking a backup")
        self.services("stop")
        result = subprocess.run(["pgrep", "-u", str(pwd.getpwnam("dev").pw_uid)], capture_output=True)
        if result.returncode != 1:
            raise RuntimeError("dev still has processes (SSH/tmux/background jobs). Close them before backup")

    def snapshots(self):
        return json.loads(self.restic("snapshots", "--json", "--tag", self.tag))

    def restore(self):
        if (BASE / "restored").exists():
            return
        try:
            snapshots = self.snapshots()
        except RuntimeError:
            if self.cfg["RESTIC_INIT"] != "true" or self.cfg["RESTORE_MODE"] != "fresh":
                raise
            self.restic("init")
            snapshots = self.snapshots()
        if self.cfg["RESTORE_MODE"] == "fresh":
            if snapshots:
                raise RuntimeError("Existing snapshots found. Use RESTORE_MODE=auto to preserve history")
        else:
            if not snapshots:
                raise RuntimeError("No matching backup exists. Use fresh only for first deployment")
            snapshot = sorted(snapshots, key=lambda s: s["time"])[-1]["id"]
            with tempfile.TemporaryDirectory(dir=BASE) as temp:
                self.restic("restore", snapshot, "--target", temp, "--verify")
                stage = Path(temp) / str(BASE / "backup").lstrip("/")
                verify_manifest(stage, self.cfg)
                for source, name in (("codex", ".codex"), ("cloudcli", ".cloudcli")):
                    dest = DEV_HOME / name
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(stage / source, dest)
                if self.cfg["PERSIST_CODEX_AUTH"] != "true":
                    (DEV_HOME / ".codex/auth.json").unlink(missing_ok=True)
                shutil.copyfile(stage / "projects.json", BASE / "restored-projects.json")
        (BASE / "restored").write_text("ok\n")

    def backup(self, nonce, leave_stopped=False):
        try:
            self.quiesce()
            inventory = git_inventory()
            stage = BASE / "backup"
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir(mode=0o700)
            copy_state(DEV_HOME / ".codex", stage / "codex", self.cfg["PERSIST_CODEX_AUTH"] != "true", skip=("tmp",))
            copy_state(DEV_HOME / ".cloudcli", stage / "cloudcli")
            (stage / "projects.json").write_text(json.dumps(inventory, indent=2))
            make_manifest(stage, self.cfg)
            output = self.restic("backup", str(stage), "--tag", self.tag, "--json")
            summaries = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
            snapshot = next(x["snapshot_id"] for x in summaries if x.get("message_type") == "summary")
            with tempfile.TemporaryDirectory(dir=BASE) as temp:
                self.restic("restore", snapshot, "--target", temp, "--verify")
                verify_manifest(Path(temp) / str(stage).lstrip("/"), self.cfg)
            receipt = {"server_id": self.cfg["server_id"], "instance": self.cfg["instance"],
                       "nonce": nonce, "snapshot": snapshot, "verified": True}
            (BASE / "last-backup.json").write_text(json.dumps(receipt))
        except BaseException:
            self.services("start")
            raise
        if not leave_stopped:
            self.services("start")
        return receipt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["restore", "backup", "prepare-destroy", "status", "resume"])
    parser.add_argument("nonce", nargs="?")
    args = parser.parse_args()
    os.umask(0o077)
    BASE.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text())
    state = State(cfg)
    with (BASE / "operation.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "restore":
            state.restore()
        elif args.action == "resume":
            state.services("start")
            print("Services resumed")
        elif args.action in ("backup", "prepare-destroy"):
            if not args.nonce:
                raise RuntimeError("Missing operation nonce")
            print(json.dumps(state.backup(args.nonce, args.action == "prepare-destroy")))
        else:
            result = {"installed": (BASE / "ready").exists(), "last_backup": None}
            for service in ("workbench-cloudcli", "workbench-tunnel", "workbench-bootstrap"):
                p = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True)
                result[service] = p.stdout.strip()
            try:
                with urllib.request.urlopen("http://127.0.0.1:3001/health", timeout=5) as response:
                    result["cloudcli_health"] = response.status
            except Exception:
                result["cloudcli_health"] = "unreachable"
            repos = []
            if WORKSPACE.exists():
                for directory in sorted(WORKSPACE.iterdir()):
                    if (directory / ".git").exists():
                        try:
                            git = ["git", "-C", str(directory)]
                            repos.append({"path": str(directory),
                                          "branch": dev_run(git + ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
                                          "tracked_files": len(dev_run(git + ["ls-files"]).splitlines())})
                        except Exception as exc:
                            repos.append({"path": str(directory), "error": str(exc)})
            result["workspace_repos"] = repos
            if (BASE / "last-backup.json").exists():
                result["last_backup"] = json.loads((BASE / "last-backup.json").read_text())["snapshot"]
            print(json.dumps(result, indent=2))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("State operation failed: " + str(exc), file=__import__("sys").stderr)
        raise SystemExit(1)
